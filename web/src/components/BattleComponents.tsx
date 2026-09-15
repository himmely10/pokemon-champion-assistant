import { AlertTriangle, Check, Edit3, Gauge, ShieldAlert, Sparkles, Zap } from 'lucide-react'
import type { Move, Pokemon, PokemonDetail } from '../model'

const typeColors: Record<string, string> = {
  一般: '#737d89', 火: '#cf6839', 水: '#397dc3', 电: '#9a7a00', 草: '#3d9265',
  冰: '#398f9c', 格斗: '#b25356', 毒: '#9662ae', 地面: '#aa7542', 飞行: '#6c6eaf',
  超能力: '#c25b85', 虫: '#718026', 岩石: '#8a7945', 幽灵: '#7662a3', 龙: '#5265b3',
  恶: '#66606a', 钢: '#5e7a83', 妖精: '#b75d91',
}

export function TypeBadge({ type }: { type: string }) {
  return <span className="type-badge" style={{ backgroundColor: typeColors[type] ?? '#607389' }}>{type}</span>
}

function MatchupSide({ pokemon, detail, align }: { pokemon: Pokemon; detail: PokemonDetail | null; align: 'left' | 'right' }) {
  const groups = [
    ['弱点', detail?.matchups.weakness ?? []],
    ['抗性', detail?.matchups.resistance ?? []],
    ['免疫', detail?.matchups.immune ?? []],
  ] as const
  return <div className={`matchup-side ${align}`}>
    <div className="matchup-side-title"><strong>{pokemon.name}</strong><span>纯属性防守相性</span></div>
    <div className="matchup-groups">{groups.map(([label, rows]) => <div className="matchup-group" key={label}><small>{label}</small><div>{rows.length ? rows.map(row => <span className="matchup-tag" key={`${label}-${row.type}`}><TypeBadge type={row.type} /><b>{row.multiplier}×</b></span>) : <span className="matchup-none">—</span>}</div></div>)}</div>
  </div>
}

export function MatchupStrip({ own, rival, ownDetail, rivalDetail }: { own: Pokemon; rival: Pokemon; ownDetail: PokemonDetail | null; rivalDetail: PokemonDetail | null }) {
  return <section className="matchup-strip" aria-label="双方属性克制情况">
    <MatchupSide pokemon={own} detail={ownDetail} align="left" />
    <span className="matchup-strip-axis" aria-hidden="true">属性</span>
    <MatchupSide pokemon={rival} detail={rivalDetail} align="right" />
  </section>
}

export function PokemonSlot({ pokemon, side, selected, scanning, onSelect }: {
  pokemon?: Pokemon
  side: 'own' | 'rival'
  selected?: boolean
  scanning?: boolean
  onSelect?: () => void
}) {
  const status = scanning ? 'scanning' : pokemon?.status ?? 'confirmed'
  return (
    <button
      type="button"
      className={`pokemon-slot ${side} ${selected ? 'selected' : ''} ${status}`}
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={pokemon ? `${side === 'own' ? '我方' : '对手'}宝可梦：${pokemon.name}${status === 'review' ? '，需要确认' : ''}` : '等待识别'}
    >
      <span className="slot-state" aria-hidden="true">
        {status === 'review' && <AlertTriangle size={14} />}
        {status === 'corrected' && <Edit3 size={13} />}
        {status === 'scanning' && <span className="scan-dot" />}
        {status === 'confirmed' && selected && <Check size={13} />}
      </span>
      {pokemon ? <img src={pokemon.image} alt="" /> : <span className="slot-number">—</span>}
      <span className="slot-copy">
        <strong>{pokemon?.name ?? '等待识别'}</strong>
        <small>{status === 'review' ? '需要确认' : status === 'corrected' ? '已修正' : pokemon?.types.join(' / ')}</small>
      </span>
    </button>
  )
}

export function DamageBar({ move, side = 'own' }: { move: Move; side?: 'own' | 'rival' }) {
  const [min, max] = move.damage ?? [0, 0]
  return (
    <div className="damage-result" aria-label={`${move.name}，伤害 ${min}% 到 ${max}%，${move.verdict}`}>
      <div className="damage-bar-copy">
        <span>{min}–{max}%</span>
        <strong>{move.verdict}</strong>
      </div>
      <div className="damage-track" aria-hidden="true">
        <span className="threshold half" />
        <span className="threshold full" />
        <span
          className={`damage-range ${side}`}
          style={{ left: `${Math.min(min, 100)}%`, width: `${Math.max(4, Math.min(max, 100) - Math.min(min, 100))}%` }}
        />
        {max > 100 && <span className={`overflow-arrow ${side}`}>›</span>}
      </div>
    </div>
  )
}

export function VerdictStack({ own, rival }: { own: Pokemon; rival: Pokemon }) {
  const faster = own.speed > rival.speed
  return (
    <div className="verdict-stack">
      <div className={`verdict-card ${faster ? 'advantage' : 'danger'}`}>
        <div className="verdict-icon"><Gauge size={20} /></div>
        <div><small>基础速度</small><strong>{faster ? '我方较高' : '对手较高'}</strong><span>{own.speed} / {rival.speed}</span></div>
      </div>
      <div className="verdict-card danger">
        <div className="verdict-icon"><ShieldAlert size={20} /></div>
        <div><small>对手属性</small><strong>{rival.types.join(' / ')}</strong><span>进入资料页核对弱点与抵抗</span></div>
      </div>
      <div className="verdict-card spark">
        <div className="verdict-icon"><Zap size={20} /></div>
        <div><small>本回合关注</small><strong>使用已保存配置计算</strong><span>伤害页会调用本地规则引擎</span></div>
      </div>
    </div>
  )
}

export function PokemonIdentity({ pokemon, align = 'left' }: { pokemon: Pokemon; align?: 'left' | 'right' }) {
  return (
    <div className={`pokemon-identity ${align}`}>
      <img src={pokemon.image} alt={`宝可梦：${pokemon.name}`} />
      <div>
        <span>#{pokemon.dex}</span>
        <h2>{pokemon.name}</h2>
        <div className="type-row">{pokemon.types.map(type => <TypeBadge key={type} type={type} />)}</div>
      </div>
    </div>
  )
}

export function CompactStat({ icon, label, value }: { icon: 'speed' | 'threat' | 'spark'; label: string; value: string }) {
  const Icon = icon === 'speed' ? Gauge : icon === 'threat' ? ShieldAlert : Sparkles
  return <div className="compact-stat"><Icon size={17} /><span>{label}</span><strong>{value}</strong></div>
}
