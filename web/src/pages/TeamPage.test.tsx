// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TeamPage } from './TeamPage'
import { api } from '../api'
import type { AppSettings, Pokemon, Team, TeamMember, TeamOptions } from '../model'

vi.mock('../api', () => ({ api: { teamOptions: vi.fn(), searchPokemon: vi.fn(), saveTeam: vi.fn(), deleteTeam: vi.fn() } }))
vi.mock('./TeamImportPanel', () => ({ TeamImportPanel: ({ onDraft }: { onDraft: (team: Team, notice: string) => void }) =>
  <button type="button" onClick={() => onDraft(importedTeam(), 'OCR 草稿：请核对。')}>模拟复核完成</button>,
}))

const pokemon: Pokemon = {
  id: 'pokemon-1', name: '妙蛙花', dex: '0003', image: '/sprite.png', types: ['草', '毒'], speed: 80,
  family_base: { id: 'pokemon-1', name: '妙蛙花', dex: '0003', image: '/sprite.png', types: ['草', '毒'], speed: 80 },
  is_battle_form: false,
}
const pokemon2: Pokemon = { ...pokemon, id: 'pokemon-2', name: '喷火龙', family_base: { ...pokemon.family_base, id: 'pokemon-2', name: '喷火龙' } }
const member: TeamMember = {
  identity: pokemon.id, points: { hp: 0, attack: 0, defense: 0, special_attack: 0, special_defense: 0, speed: 0 },
  nature: null, ability: null, item: null, moves: [null, null, null, null], pokemon,
}
const settings: AppSettings = {
  host: '127.0.0.1', port: 4455, source: '', theme: 'light', reduced_motion: false,
  password_in_memory: false, password_saved: false, user_directory: 'test',
}

function importedTeam(): Team { return { id: '', revision: 0, name: '截图导入队伍', registration: 'partial', members: [member] } }
function savedTeam(): Team { return { id: 'old-team', revision: 1, name: '已有队伍', registration: 'partial', members: [member] } }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.teamOptions).mockRejectedValue(new Error('unavailable'))
  vi.mocked(api.searchPokemon).mockResolvedValue([pokemon])
})
afterEach(cleanup)

describe('TeamPage import integration', () => {
  it('keeps the import entry visible in an empty repository and never auto-saves a reviewed draft', async () => {
    const onPendingChange = vi.fn()
    render(<TeamPage teams={[]} featured={[pokemon]} selectedTeamId={null} settings={settings} onSelectedTeam={vi.fn()} onRefresh={vi.fn()} onPendingChange={onPendingChange} />)
    await userEvent.click(screen.getByRole('button', { name: '截图导入队伍' }))
    await userEvent.click(screen.getByRole('button', { name: '模拟复核完成' }))
    expect(screen.getByText('未保存的导入队伍')).toBeTruthy()
    expect(api.saveTeam).not.toHaveBeenCalled()
    expect(onPendingChange).toHaveBeenCalledWith(true)
  })

  it('does not present an old saved team as selected or deletable while editing imported draft', async () => {
    render(<TeamPage teams={[savedTeam()]} featured={[pokemon]} selectedTeamId="old-team" settings={settings} onSelectedTeam={vi.fn()} onRefresh={vi.fn()} onPendingChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '截图导入队伍' }))
    await userEvent.click(screen.getByRole('button', { name: '模拟复核完成' }))
    expect(screen.getByText('未保存的导入队伍')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '删除队伍' })).toBeNull()
    expect(document.querySelector('.team-list-panel > button.active')).toBeNull()
  })

  it('prompts before discarding an unsaved import on team switch', async () => {
    const onSelectedTeam = vi.fn()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<TeamPage teams={[savedTeam()]} featured={[pokemon]} selectedTeamId="old-team" settings={settings} onSelectedTeam={onSelectedTeam} onRefresh={vi.fn()} onPendingChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '截图导入队伍' }))
    await userEvent.click(screen.getByRole('button', { name: '模拟复核完成' }))
    await userEvent.click(screen.getByRole('button', { name: /已有队伍/ }))
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
    expect(onSelectedTeam).not.toHaveBeenCalled()
    expect(screen.getByText('未保存的导入队伍')).toBeTruthy()
    confirm.mockRestore()
  })

  it('keeps a newly created draft when a saved team was previously selected', async () => {
    render(<TeamPage teams={[savedTeam()]} featured={[pokemon]} selectedTeamId="old-team" settings={settings} onSelectedTeam={vi.fn()} onRefresh={vi.fn()} onPendingChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '创建队伍' }))
    expect((screen.getByRole('textbox', { name: '队伍名称' }) as HTMLInputElement).value).toBe('新队伍')
    expect(screen.getByText('有未保存更改')).toBeTruthy()
  })

  it('keeps a duplicate draft when a saved team was previously selected', async () => {
    render(<TeamPage teams={[savedTeam()]} featured={[pokemon]} selectedTeamId="old-team" settings={settings} onSelectedTeam={vi.fn()} onRefresh={vi.fn()} onPendingChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '复制当前队伍' }))
    expect((screen.getByRole('textbox', { name: '队伍名称' }) as HTMLInputElement).value).toBe('已有队伍 副本')
    expect(screen.getByText('有未保存更改')).toBeTruthy()
  })

  it('retains the saved record when list refresh fails after a successful save', async () => {
    vi.mocked(api.saveTeam).mockResolvedValue({ ...importedTeam(), id: 'new-team', revision: 1 })
    const onRefresh = vi.fn().mockRejectedValue(new Error('refresh failed'))
    render(<TeamPage teams={[]} featured={[pokemon]} selectedTeamId={null} settings={settings} onSelectedTeam={vi.fn()} onRefresh={onRefresh} onPendingChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '截图导入队伍' }))
    await userEvent.click(screen.getByRole('button', { name: '模拟复核完成' }))
    await userEvent.click(screen.getByRole('button', { name: '保存队伍' }))
    await waitFor(() => expect(screen.getByText(/队伍已保存，但列表刷新失败/)).toBeTruthy())
    expect(api.saveTeam).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '已保存' }).hasAttribute('disabled')).toBe(true)
  })

  it('locks editing and team switching until an in-flight save resolves', async () => {
    let resolveSave!: (value: Team) => void
    vi.mocked(api.saveTeam).mockImplementation(() => new Promise(resolve => { resolveSave = resolve }))
    render(<TeamPage teams={[savedTeam()]} featured={[pokemon]} selectedTeamId="old-team" settings={settings} onSelectedTeam={vi.fn()} onRefresh={vi.fn().mockResolvedValue(undefined)} onPendingChange={vi.fn()} />)
    await userEvent.type(screen.getByRole('textbox', { name: '队伍名称' }), '改')
    await userEvent.click(screen.getByRole('button', { name: '保存队伍' }))
    expect(screen.getByRole('textbox', { name: '队伍名称' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '截图导入队伍' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: /已有队伍1\/6/ }).hasAttribute('disabled')).toBe(true)
    resolveSave({ ...savedTeam(), name: '已有队伍改', revision: 2 })
    await waitFor(() => expect(screen.getByRole('textbox', { name: '队伍名称' }).hasAttribute('disabled')).toBe(false))
    expect((screen.getByRole('textbox', { name: '队伍名称' }) as HTMLInputElement).value).toBe('已有队伍改')
  })

  it('ignores a late options response from the previous Pokémon identity', async () => {
    let resolveOld!: (value: TeamOptions) => void
    vi.mocked(api.teamOptions)
      .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
      .mockResolvedValueOnce({ pokemon: pokemon2, natures: [], abilities: [{ id: 'new-ability', name: '新特性' }], items: [], moves: [], point_rules: { per_stat: 32, total: 66 } })
    vi.mocked(api.searchPokemon).mockResolvedValue([pokemon, pokemon2])
    render(<TeamPage teams={[savedTeam()]} featured={[pokemon, pokemon2]} selectedTeamId="old-team" settings={settings} onSelectedTeam={vi.fn()} onRefresh={vi.fn()} onPendingChange={vi.fn()} />)
    await userEvent.selectOptions(screen.getByRole('combobox', { name: '宝可梦 / 形态' }), pokemon2.id)
    await screen.findByRole('option', { name: '新特性' })
    resolveOld({ pokemon, natures: [], abilities: [{ id: 'old-ability', name: '旧特性' }], items: [], moves: [], point_rules: { per_stat: 32, total: 66 } })
    await waitFor(() => expect(screen.queryByRole('option', { name: '旧特性' })).toBeNull())
  })
})
