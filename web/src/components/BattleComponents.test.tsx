// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { DamageBar } from './BattleComponents'
import type { Move } from '../model'

const move = (damage: [number, number]): Move => ({
  name: '水流裂破', type: '水', category: '物理', power: 85, accuracy: 100,
  usage: null, damage, verdict: '确定击杀', description: '',
})

afterEach(cleanup)

describe('DamageBar', () => {
  it('keeps an entirely over-100% range inside the damage track', () => {
    const { container } = render(<DamageBar move={move([107.2, 126.8])} />)
    expect(screen.getByText('107.2–126.8%')).toBeTruthy()
    expect(container.querySelector('.damage-range')).toBeNull()
    const marker = container.querySelector('.damage-limit-marker.overflow')
    expect(marker?.textContent).toBe('+')
    expect(marker?.parentElement?.classList.contains('damage-track')).toBe(true)
  })

  it('clips a crossing range at the 100% threshold and adds an overflow marker', () => {
    const { container } = render(<DamageBar move={move([92, 110])} side="rival" />)
    const range = container.querySelector('.damage-range') as HTMLElement
    expect(range.style.left).toBe('92%')
    expect(range.style.width).toBe('8%')
    expect(container.querySelector('.damage-limit-marker.rival.overflow')).toBeTruthy()
  })

  it('renders a normal range without an overflow marker', () => {
    const { container } = render(<DamageBar move={move([37.3, 44.4])} />)
    expect(container.querySelector('.damage-range')).toBeTruthy()
    expect(container.querySelector('.damage-limit-marker')).toBeNull()
  })

  it('shows the conditional KO chance for a random knockout', () => {
    const randomKo = { ...move([92.6, 108.9]), verdict: '乱数击杀', ko_chance: 37.5 }
    render(<DamageBar move={randomKo} />)
    expect(screen.getByText('命中后 37.5% 概率击杀')).toBeTruthy()
    expect(screen.getByLabelText(/命中后 37.5% 概率击杀/)).toBeTruthy()
  })
})
