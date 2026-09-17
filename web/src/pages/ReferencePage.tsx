import { useEffect, useState } from 'react'
import { BookOpen, ChevronRight, Search } from 'lucide-react'
import { api } from '../api'
import type { Pokemon, PokemonDetail } from '../model'
import { TypeBadge } from '../components/BattleComponents'

const statLabels: Record<string, string> = { hp: 'HP', attack: '攻击', defense: '防御', special_attack: '特攻', special_defense: '特防', speed: '速度' }

export function ReferencePage({ featured, onOpenDamage }: { featured: Pokemon[]; onOpenDamage: (pokemon: Pokemon) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Pokemon[]>(featured)
  const [selectedId, setSelectedId] = useState(featured[0]?.id ?? '')
  const [detailResult, setDetail] = useState<PokemonDetail | null>(null)
  const [tab, setTab] = useState<'overview' | 'moves' | 'forms'>('overview')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const timer = window.setTimeout(async () => {
      try {
        const items: Pokemon[] = []
        const pageSize = 500
        let page: Pokemon[]
        do {
          page = await api.searchPokemon(query, pageSize, items.length)
          items.push(...page)
        } while (active && page.length === pageSize)
        if (!active) return
        setResults(items)
        setSelectedId(current => items.some(item => item.id === current) ? current : items[0]?.id ?? '')
        setError('')
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : '搜索失败')
      }
    }, 180)
    return () => { active = false; window.clearTimeout(timer) }
  }, [query])

  useEffect(() => {
    let active = true
    if (!selectedId) return
    api.pokemonDetail(selectedId).then(item => { if (active) setDetail(item) }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : '资料读取失败') })
    return () => { active = false }
  }, [selectedId])

  const detail = detailResult?.id === selectedId ? detailResult : null
  const pokemon = detail ?? results.find(item => item.id === selectedId)
  return <div className="standard-page library-page">
    <section className="library-search"><div><p className="eyebrow">本地资料</p><h2>宝可梦资料库</h2></div><label><Search size={20} /><span className="sr-only">搜索宝可梦</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索名称、属性或英文键名" /></label></section>
    {error && <div className="inline-error">{error}</div>}
    <section className="library-layout">
      <aside className="result-list" aria-label="宝可梦目录"><div className="result-count">{results.length} 个结果</div>{results.map(item => <button key={item.id} type="button" className={selectedId === item.id ? 'active' : ''} onClick={() => setSelectedId(item.id)}><img src={item.image} alt="" loading="lazy" /><span><strong>{item.name}</strong><small>#{item.dex} · {item.types.join(' / ')}</small></span><ChevronRight size={17} /></button>)}</aside>
      {pokemon ? <article className="dex-entry" aria-label={`${pokemon.name}资料`}>
        <header><img src={pokemon.image} alt={`宝可梦：${pokemon.name}`} /><div><small>全国图鉴 #{pokemon.dex}</small><h2>{pokemon.name}</h2><div className="type-row">{pokemon.types.map(type => <TypeBadge key={type} type={type} />)}</div></div><button className="button primary" type="button" onClick={() => onOpenDamage(pokemon)}>作为对手打开计算</button></header>
        <div className="dex-tabs"><button type="button" className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>概览</button><button type="button" className={tab === 'moves' ? 'active' : ''} onClick={() => setTab('moves')}>招式</button><button type="button" className={tab === 'forms' ? 'active' : ''} onClick={() => setTab('forms')}>形态</button></div>
        {tab === 'overview' && <>
          <section className="dex-section"><div className="section-title"><div><small>种族值</small><h3>基础能力</h3></div><span>总和 {detail?.base_stat_total ?? '—'}</span></div><div className="stat-bars">{Object.entries(detail?.base_stats ?? {}).map(([name, value]) => <div key={name}><span>{statLabels[name] ?? name}</span><div><i style={{ width: `${Number(value) / 255 * 100}%` }} /></div><strong>{value}</strong></div>)}</div></section>
          <section className="dex-section"><div className="section-title"><div><small>属性相性</small><h3>弱点、抵抗与无效</h3></div></div><div className="dex-matchups"><MatchupGroup label="弱点" rows={detail?.matchups.weakness ?? []} /><MatchupGroup label="抵抗 / 无效" rows={[...(detail?.matchups.resistance ?? []), ...(detail?.matchups.immune ?? [])]} /></div></section>
        </>}
        {tab === 'moves' && <section className="dex-section"><div className="section-title"><div><small>采用率快照</small><h3>当前形态招式池</h3></div><span>{detail?.moves.length ?? 0} 项</span></div><div className="compact-moves">{detail?.moves.map(move => <div key={move.id ?? move.name}><strong>{move.name}</strong><TypeBadge type={move.type} /><span>{move.usage === null ? '—' : `${move.usage}%`}</span><small>{move.description}</small></div>)}</div><p className="source-notice">{detail?.notice}</p></section>}
        {tab === 'forms' && <section className="dex-section"><div className="section-title"><div><small>形态家族</small><h3>可用形态</h3></div></div><div className="form-family">{detail?.forms.map(form => <button type="button" key={form.id} onClick={() => setSelectedId(form.id)}><img src={form.image} alt="" /><strong>{form.name}</strong><span>{form.types.join(' / ')}</span></button>)}</div></section>}
        <section className="dex-section"><div className="section-title"><div><small>本地来源</small><h3>资料说明</h3></div><button className="text-button" type="button" onClick={() => setTab('moves')}><BookOpen size={16} />查看招式</button></div><p className="source-notice">{detail?.notice ?? '正在读取资料。'}</p></section>
      </article> : <div className="empty-battle"><h2>没有匹配结果</h2><p>请尝试名称、属性或英文键名。</p></div>}
    </section>
  </div>
}

function MatchupGroup({ label, rows }: { label: string; rows: Array<{ type: string; multiplier: number }> }) {
  return <div><span>{label}</span>{rows.map(row => <span className="matchup-tag" key={`${label}-${row.type}`}><TypeBadge type={row.type} /><b>{row.multiplier}×</b></span>)}</div>
}
