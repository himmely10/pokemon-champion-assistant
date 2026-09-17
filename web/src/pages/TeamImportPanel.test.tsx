// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TeamImportPanel } from './TeamImportPanel'
import { api, ApiError } from '../api'
import type { AppSettings, TeamImportRecognition } from '../model'

vi.mock('../api', () => ({ ApiError: class extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status } }, api: {
  teamImportRecognize: vi.fn(), teamImportCombine: vi.fn(), teamImportObsCapture: vi.fn(),
  saveSettings: vi.fn(), obsSources: vi.fn(), searchPokemon: vi.fn(),
} }))

const settings: AppSettings = {
  host: '127.0.0.1', port: 4455, source: '游戏', theme: 'light', reduced_motion: false,
  password_in_memory: true, password_saved: true, user_directory: 'test',
}

function recognition(mode: 'ability' | 'status', code = 'ABCDEF1234'): TeamImportRecognition {
  return { handle: `${mode}-${code}`, page: {
    mode, team_code: code, code_evidence: { text: `ID: ${code}`, score: 0.99 },
    members: Array.from({ length: 6 }, (_, index) => ({
      slot: index + 1, member: { identity: `pokemon-${index + 1}` },
      evidence: { name: { text: `宝可梦${index + 1}`, score: 0.98 } },
    })), source: { sha256: code, size: [1920, 1080] },
  } }
}

function upload(index: number, name: string) {
  const inputs = document.querySelectorAll<HTMLInputElement>('input[type=file]')
  fireEvent.change(inputs[index], { target: { files: [new File(['image'], name, { type: 'image/png' })] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => `blob:test-${Math.random()}`), revokeObjectURL: vi.fn() })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('TeamImportPanel', () => {
  it('requires both page reviews before loading a new unsaved draft', async () => {
    vi.mocked(api.teamImportRecognize).mockImplementation(async (_, mode) => recognition(mode))
    vi.mocked(api.teamImportCombine).mockResolvedValue({
      draft: { id: '', revision: 0, name: '截图导入 ABCDEF1234', registration: 'full', members: [] },
      warnings: [], notice: '请核对后保存。',
    })
    const onDraft = vi.fn()
    render(<TeamImportPanel settings={settings} onDraft={onDraft} onCancel={vi.fn()} />)
    upload(0, 'ability.png')
    upload(1, 'status.png')
    await screen.findByRole('button', { name: '确认能力页已核对' })
    const load = screen.getByRole('button', { name: '载入未保存草稿' })
    expect(load.hasAttribute('disabled')).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: '确认能力页已核对' }))
    expect(load.hasAttribute('disabled')).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: '确认状态页已核对' }))
    await userEvent.click(load)
    await waitFor(() => expect(onDraft).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.teamImportCombine).mock.calls[0][0]).toMatchObject({
      ability_handle: 'ability-ABCDEF1234', status_handle: 'status-ABCDEF1234',
      ability_review: { code: 'ABCDEF1234', identities: ['pokemon-1', 'pokemon-2', 'pokemon-3', 'pokemon-4', 'pokemon-5', 'pokemon-6'] },
    })
    expect(onDraft.mock.calls[0][0].id).toBe('')
  })

  it('ignores an older OCR response after replacing an image', async () => {
    let resolveOld!: (value: TeamImportRecognition) => void
    vi.mocked(api.teamImportRecognize)
      .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
      .mockResolvedValueOnce(recognition('ability', 'NEWCODE123'))
    render(<TeamImportPanel settings={settings} onDraft={vi.fn()} onCancel={vi.fn()} />)
    upload(0, 'old.png')
    upload(0, 'new.png')
    await screen.findByDisplayValue('NEWCODE123')
    resolveOld(recognition('ability', 'OLDCODE123'))
    await waitFor(() => expect(screen.queryByDisplayValue('OLDCODE123')).toBeNull())
    expect(screen.getByDisplayValue('NEWCODE123')).toBeTruthy()
  })

  it('re-recognizes the same image while revoking the old review confirmation', async () => {
    vi.mocked(api.teamImportRecognize).mockResolvedValue(recognition('ability'))
    render(<TeamImportPanel settings={settings} onDraft={vi.fn()} onCancel={vi.fn()} />)
    upload(0, 'ability.png')
    await userEvent.click(await screen.findByRole('button', { name: '确认能力页已核对' }))
    expect(screen.getByRole('button', { name: '已核对（点击撤销）' })).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '重新识别原图' }))
    await screen.findByRole('button', { name: '确认能力页已核对' })
    const calls = vi.mocked(api.teamImportRecognize).mock.calls
    expect(calls).toHaveLength(2)
    expect(calls[1][0]).toBe(calls[0][0])
  })

  it('does not accept a late combine response after a reviewed page changes', async () => {
    let resolveCombine!: (value: { draft: { id: string; revision: number; name: string; registration: 'full'; members: [] }; warnings: string[]; notice: string }) => void
    vi.mocked(api.teamImportRecognize).mockImplementation(async (_, mode) => recognition(mode))
    vi.mocked(api.teamImportCombine).mockImplementation(() => new Promise(resolve => { resolveCombine = resolve }))
    const onDraft = vi.fn()
    render(<TeamImportPanel settings={settings} onDraft={onDraft} onCancel={vi.fn()} />)
    upload(0, 'ability.png')
    upload(1, 'status.png')
    await userEvent.click(await screen.findByRole('button', { name: '确认能力页已核对' }))
    await userEvent.click(screen.getByRole('button', { name: '确认状态页已核对' }))
    await userEvent.click(screen.getByRole('button', { name: '载入未保存草稿' }))
    fireEvent.change(screen.getByRole('textbox', { name: '能力页队伍码' }), { target: { value: 'CHANGED123' } })
    resolveCombine({ draft: { id: '', revision: 0, name: '旧草稿', registration: 'full', members: [] }, warnings: [], notice: '' })
    await waitFor(() => expect(screen.getByDisplayValue('CHANGED123')).toBeTruthy())
    expect(onDraft).not.toHaveBeenCalled()
  })

  it('disables combining old handles as soon as a new OBS capture begins', async () => {
    vi.mocked(api.teamImportRecognize).mockImplementation(async (_, mode) => recognition(mode))
    vi.mocked(api.teamImportObsCapture).mockImplementation(() => new Promise(() => undefined))
    render(<TeamImportPanel settings={settings} onDraft={vi.fn()} onCancel={vi.fn()} />)
    upload(0, 'ability.png')
    upload(1, 'status.png')
    await userEvent.click(await screen.findByRole('button', { name: '确认能力页已核对' }))
    await userEvent.click(screen.getByRole('button', { name: '确认状态页已核对' }))
    expect(screen.getByRole('button', { name: '载入未保存草稿' }).hasAttribute('disabled')).toBe(false)
    await userEvent.click(screen.getAllByRole('button', { name: '从 OBS 截图' })[0])
    expect(screen.getByRole('button', { name: '载入未保存草稿' }).hasAttribute('disabled')).toBe(true)
  })

  it('re-recognizes the original blobs after an expired handle response', async () => {
    vi.mocked(api.teamImportRecognize).mockImplementation(async (_, mode) => recognition(mode))
    vi.mocked(api.teamImportCombine).mockRejectedValue(new ApiError('截图复核已过期，请重新识别。', 409))
    render(<TeamImportPanel settings={settings} onDraft={vi.fn()} onCancel={vi.fn()} />)
    upload(0, 'ability.png')
    upload(1, 'status.png')
    await userEvent.click(await screen.findByRole('button', { name: '确认能力页已核对' }))
    await userEvent.click(screen.getByRole('button', { name: '确认状态页已核对' }))
    await userEvent.click(screen.getByRole('button', { name: '载入未保存草稿' }))
    await waitFor(() => expect(api.teamImportRecognize).toHaveBeenCalledTimes(4))
    const calls = vi.mocked(api.teamImportRecognize).mock.calls
    expect(calls[2][0]).toBe(calls[0][0])
    expect(calls[3][0]).toBe(calls[1][0])
    expect(screen.getByRole('button', { name: '确认能力页已核对' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '确认状态页已核对' })).toBeTruthy()
  })

  it('reports a failed automatic re-recognition without claiming both pages succeeded', async () => {
    vi.mocked(api.teamImportRecognize).mockImplementationOnce(async () => recognition('ability'))
      .mockImplementationOnce(async () => recognition('status'))
      .mockRejectedValueOnce(new Error('能力页 OCR 失败'))
      .mockImplementationOnce(async () => recognition('status'))
    vi.mocked(api.teamImportCombine).mockRejectedValue(new ApiError('截图复核已过期，请重新识别。', 409))
    render(<TeamImportPanel settings={settings} onDraft={vi.fn()} onCancel={vi.fn()} />)
    upload(0, 'ability.png')
    upload(1, 'status.png')
    await userEvent.click(await screen.findByRole('button', { name: '确认能力页已核对' }))
    await userEvent.click(screen.getByRole('button', { name: '确认状态页已核对' }))
    await userEvent.click(screen.getByRole('button', { name: '载入未保存草稿' }))
    await screen.findByText('部分原图重新识别失败；请查看对应页面错误并重试，之后重新核对两页。')
    expect(screen.getByText('能力页 OCR 失败')).toBeTruthy()
    expect(screen.getByRole('button', { name: '载入未保存草稿' }).hasAttribute('disabled')).toBe(true)
  })
})
