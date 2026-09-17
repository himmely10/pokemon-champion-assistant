// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { api } from './api'
import type { Bootstrap, Pokemon, Team } from './model'

vi.mock('./api', () => ({ api: { bootstrap: vi.fn(), searchPokemon: vi.fn(), teamOptions: vi.fn(), saveTeam: vi.fn() } }))
vi.mock('./components/AppShell', () => ({ AppShell: ({ onPageChange, children }: { onPageChange: (page: string) => void; children: React.ReactNode }) =>
  <div><button onClick={() => onPageChange('teams')}>前往队伍</button><button onClick={() => onPageChange('library')}>前往资料</button>{children}</div>,
}))
vi.mock('./pages/BattlePage', () => ({ BattlePage: () => <div>对战台页面</div> }))
vi.mock('./pages/ReferencePage', () => ({ ReferencePage: () => <div>资料页面</div> }))
vi.mock('./pages/TeamImportPanel', () => ({ TeamImportPanel: ({ onDraft }: { onDraft: (team: Team, notice: string) => void }) =>
  <button onClick={() => onDraft({ id: '', revision: 0, name: '导入草稿', registration: 'partial', members: [member] }, '待核对')}>模拟导入</button>,
}))

const pokemon: Pokemon = {
  id: 'pokemon-1', name: '妙蛙花', dex: '0003', image: '/sprite.png', types: ['草', '毒'], speed: 80,
  family_base: { id: 'pokemon-1', name: '妙蛙花', dex: '0003', image: '/sprite.png', types: ['草', '毒'], speed: 80 },
  is_battle_form: false,
}
const member: Team['members'][number] = {
  identity: pokemon.id, points: { hp: 0, attack: 0, defense: 0, special_attack: 0, special_defense: 0, speed: 0 },
  nature: null, ability: null, item: null, moves: [null, null, null, null], pokemon,
}
const bootstrap: Bootstrap = {
  app: { name: 'Champion Lab', version: '0.4.1', dataset_id: 'test', pokemon_forms: 1, api: 'local' },
  settings: { host: '127.0.0.1', port: 4455, source: '', theme: 'light', reduced_motion: false, password_in_memory: false, password_saved: false, user_directory: 'test' },
  teams: [], featured: [pokemon],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.bootstrap).mockResolvedValue(bootstrap)
  vi.mocked(api.searchPokemon).mockResolvedValue([pokemon])
  vi.mocked(api.teamOptions).mockRejectedValue(new Error('unavailable'))
})
afterEach(cleanup)

it('blocks navigation away from an unsaved imported draft until confirmed', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: '前往队伍' }))
  await userEvent.click(await screen.findByRole('button', { name: '截图导入队伍' }))
  await userEvent.click(screen.getByRole('button', { name: '模拟导入' }))
  await waitFor(() => expect(screen.getByText('未保存的导入队伍')).toBeTruthy())
  await userEvent.click(screen.getByRole('button', { name: '前往资料' }))
  expect(confirm).toHaveBeenCalledTimes(1)
  expect(screen.queryByText('资料页面')).toBeNull()
  expect(api.saveTeam).not.toHaveBeenCalled()
  confirm.mockReturnValue(true)
  await userEvent.click(screen.getByRole('button', { name: '前往资料' }))
  expect(screen.getByText('资料页面')).toBeTruthy()
  confirm.mockRestore()
})
