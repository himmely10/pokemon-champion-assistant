// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReferencePage } from './ReferencePage'
import { api } from '../api'
import type { Pokemon, PokemonDetail } from '../model'

vi.mock('../api', () => ({ api: { searchPokemon: vi.fn(), pokemonDetail: vi.fn() } }))

const makePokemon = (index: number): Pokemon => ({
  id: `pokemon-${index}`, name: `宝可梦 ${index}`, dex: String(index).padStart(4, '0'),
  image: `/sprite/${index}`, types: ['水'], speed: 80,
  family_base: { id: `pokemon-${index}`, name: `宝可梦 ${index}`, dex: String(index).padStart(4, '0'), image: `/sprite/${index}`, types: ['水'], speed: 80 },
  is_battle_form: false,
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.pokemonDetail).mockImplementation(async id => ({ ...makePokemon(Number(id.split('-')[1])), base_stats: {}, base_stat_total: 0, matchups: { weakness: [], resistance: [], immune: [] }, moves: [], notice: '', forms: [], abilities: [] }) as PokemonDetail)
})
afterEach(cleanup)

describe('ReferencePage catalog', () => {
  it('loads every page and keeps directory and detail as separate scroll regions', async () => {
    const all = Array.from({ length: 501 }, (_, index) => makePokemon(index))
    vi.mocked(api.searchPokemon).mockImplementation(async (_query, _limit, offset = 0) => all.slice(offset, offset + 500))
    render(<ReferencePage featured={[all[0]]} onOpenDamage={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('501 个结果')).toBeTruthy())
    expect(api.searchPokemon).toHaveBeenCalledWith('', 500, 0)
    expect(api.searchPokemon).toHaveBeenCalledWith('', 500, 500)
    expect(screen.getByRole('complementary', { name: '宝可梦目录' }).classList.contains('result-list')).toBe(true)
    expect(screen.getByRole('article', { name: '宝可梦 0资料' }).classList.contains('dex-entry')).toBe(true)
    expect(screen.getByRole('button', { name: /宝可梦 500/ })).toBeTruthy()
  })

  it('does not show the previous Pokémon details while a new entry loads', async () => {
    const first = makePokemon(0)
    const second = makePokemon(1)
    vi.mocked(api.searchPokemon).mockResolvedValue([first, second])
    const firstDetail: PokemonDetail = {
      ...first, base_stats: {}, base_stat_total: 111,
      matchups: { weakness: [], resistance: [], immune: [] }, moves: [], notice: '', forms: [], abilities: [],
    }
    vi.mocked(api.pokemonDetail).mockImplementation(id => id === first.id ? Promise.resolve(firstDetail) : new Promise(() => {}))
    render(<ReferencePage featured={[first]} onOpenDamage={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('2 个结果')).toBeTruthy())
    await screen.findByText('总和 111')
    await userEvent.click(screen.getByRole('button', { name: /宝可梦 1/ }))
    expect(screen.getByRole('article', { name: '宝可梦 1资料' })).toBeTruthy()
    expect(screen.queryByText('总和 111')).toBeNull()
  })
})
