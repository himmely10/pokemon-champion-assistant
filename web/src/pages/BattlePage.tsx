import { useEffect, useMemo, useRef, useState } from 'react'
import { Camera, CheckCircle2, ChevronRight, CircleHelp, RotateCcw, Search, Settings2, Upload } from 'lucide-react'
import { api } from '../api'
import type { AppSettings, Move, Pokemon, PokemonDetail, RecognitionReport, Team } from '../model'
import { MatchupStrip, PokemonIdentity, PokemonSlot, TypeBadge, VerdictStack } from '../components/BattleComponents'

type BattleTab = 'summary' | 'moves' | 'types'

export function BattlePage({ teams, selectedTeamId, onTeamChange, ownTeam, rivalTeam, recognition, onRecognized, ownId, rivalId, onOwnChange, onRivalChange, settings, onOpenDamage }: {
  teams: Team[]
  selectedTeamId: string | null
  onTeamChange: (id: string) => void
  ownTeam: Pokemon[]
  rivalTeam: Pokemon[]
  recognition: RecognitionReport | null
  onRecognized: (report: RecognitionReport) => void
  ownId: string | null
  rivalId: string | null
  onOwnChange: (id: string) => void
  onRivalChange: (id: string) => void
  settings: AppSettings
  onOpenDamage: () => void
}) {
  const [tab, setTab] = useState<BattleTab>('summary')
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState('')
  const [conditionsOpen, setConditionsOpen] = useState(false)
  const [ownDetail, setOwnDetail] = useState<PokemonDetail | null>(null)
  const [detail, setDetail] = useState<PokemonDetail | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const own = ownTeam.find(item => item.id === ownId) ?? ownTeam[0]
  const rival = rivalTeam.find(item => item.id === rivalId) ?? rivalTeam[0]

  useEffect(() => {
    if (!own || !rival) return
    Promise.all([api.pokemonDetail(own.id), api.pokemonDetail(rival.id)]).then(([nextOwn, nextRival]) => {
      setOwnDetail(nextOwn)
      setDetail(nextRival)
    }).catch(() => {
      setOwnDetail(null)
      setDetail(null)
    })
  }, [own, rival])

  const runRecognition = async (operation: () => Promise<RecognitionReport>) => {
    setScanning(true)
    setScanError('')
    try {
      onRecognized(await operation())
    } catch (error) {
      setScanError(error instanceof Error ? error.message : '识别失败')
    } finally {
      setScanning(false)
    }
  }

  const title = useMemo(() => {
    if (scanning) return '正在使用本地识别器分析六个位置…'
    if (scanError) return scanError
    if (!recognition) return '请选择完整 16:9 截图，或从 OBS 抓取当前画面'
    return `识别完成：${recognition.recognized_count}/6 · ${recognition.elapsed_seconds.toFixed(2)} 秒`
  }, [recognition, scanError, scanning])
  const reviewSlots = recognition?.opponent.filter(slot => !slot.pokemon && slot.candidates?.some(candidate => candidate.pokemon)) ?? []

  const correctSlot = (slotNumber: number, pokemon: Pokemon) => {
    if (!recognition) return
    const opponent = recognition.opponent.map(slot => slot.slot === slotNumber ? { ...slot, status: 'recognized' as const, name: pokemon.name, pokemon } : slot)
    onRecognized({ ...recognition, opponent, recognized_count: opponent.filter(slot => slot.pokemon).length })
    onRivalChange(pokemon.id)
  }

  if (!own || !rival) {
    return <section className="empty-battle"><div className="empty-orbit"><span /></div><small>等待对局资料</small><h2>先准备双方阵容</h2><p>在队伍仓库选择我方队伍，然后上传对手队伍截图。</p><div><button className="button primary" type="button" onClick={() => fileInput.current?.click()}><Upload size={17} />上传截图</button></div><input ref={fileInput} hidden type="file" accept="image/png,image/jpeg,image/webp,image/bmp" onChange={event => { const file = event.target.files?.[0]; if (file) void runRecognition(() => api.recognize(file)) }} /></section>
  }

  return (
    <div className="battle-page">
      <section className="page-toolbar" aria-label="本局设置">
        <div className="team-context">
          <span className="context-label">本局我方队伍</span>
          <select className="select-like" aria-label="选择我方队伍" value={selectedTeamId ?? ''} onChange={event => onTeamChange(event.target.value)}>
            {teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
          </select>
        </div>
        <div className="toolbar-actions">
          <button className="button quiet" type="button" onClick={() => setConditionsOpen(value => !value)}><Settings2 size={17} />对局条件</button>
          <button className="button quiet" type="button" onClick={() => fileInput.current?.click()} disabled={scanning}><Upload size={17} />上传截图</button>
          <button className="button secondary" type="button" onClick={() => void runRecognition(() => api.obsCapture(settings))} disabled={scanning}><Camera size={17} />{scanning ? '正在识别…' : '从 OBS 识别'}</button>
          <input ref={fileInput} hidden type="file" accept="image/png,image/jpeg,image/webp,image/bmp" onChange={event => { const file = event.target.files?.[0]; if (file) void runRecognition(() => api.recognize(file)); event.currentTarget.value = '' }} />
        </div>
      </section>

      {conditionsOpen && <section className="inline-conditions"><strong>当前快速判断口径</strong><span>双打 · 50 级 · 无天气 · 无场地</span><button className="text-button" type="button" onClick={onOpenDamage}>在伤害计算中修改</button></section>}

      <section className="battle-stage" aria-labelledby="roster-title">
        <div className="stage-grid">
          <div className="roster-side own-side">
            <div className="roster-title"><span className="side-rule" /><div><small>我方</small><h2 id="roster-title">预存阵容</h2></div></div>
            <fieldset className="roster-grid"><legend className="sr-only">我方阵容</legend>{ownTeam.map(pokemon => <PokemonSlot key={pokemon.id} pokemon={pokemon} side="own" selected={own.id === pokemon.id} onSelect={() => onOwnChange(pokemon.id)} />)}</fieldset>
          </div>
          <div className="versus-axis" aria-hidden="true"><span>VS</span><i /></div>
          <div className="roster-side rival-side">
            <div className="roster-title rival"><span className="side-rule" /><div><small>对手</small><h2>识别阵容</h2></div></div>
            <fieldset className="roster-grid"><legend className="sr-only">对手阵容</legend>{Array.from({ length: 6 }, (_, index) => <PokemonSlot key={index} pokemon={rivalTeam[index]} side="rival" selected={rival.id === rivalTeam[index]?.id} scanning={scanning} onSelect={() => rivalTeam[index] && onRivalChange(rivalTeam[index].id)} />)}</fieldset>
          </div>
        </div>
        <output className={`analysis-status ${scanning ? 'busy' : ''} ${scanError ? 'error' : ''}`}>
          {scanning ? <span className="spinner" /> : recognition && !scanError ? <CheckCircle2 size={17} /> : <RotateCcw size={17} />}
          <span>{title}</span>
          {!scanning && <button type="button" onClick={() => fileInput.current?.click()}>{recognition ? '换一张截图' : '选择截图'}</button>}
        </output>
      </section>

      {reviewSlots.length > 0 && <section className="recognition-review"><div><strong>需要人工确认</strong><span>低分或候选接近时不会自动采用，请选择正确候选。</span></div>{reviewSlots.map(slot => <div className="review-slot" key={slot.slot}><b>位置 {slot.slot}</b>{slot.candidates?.filter(candidate => candidate.pokemon).map(candidate => <button type="button" key={candidate.name} onClick={() => candidate.pokemon && correctSlot(slot.slot, candidate.pokemon)}><img src={candidate.pokemon?.image} alt="" /><span>{candidate.name}</span><small>{candidate.similarity.toFixed(3)}</small></button>)}</div>)}</section>}

      <section className="matchup-layout">
        <div className="matchup-panel">
          <div className="matchup-heading"><div><small>当前对位</small><h2>快速判断</h2></div><button className="icon-button" type="button" aria-label="当前对位说明" title="快速判断基于当前基础速度；精确条件请进入伤害计算"><CircleHelp size={18} /></button></div>
          <div className="matchup-versus"><PokemonIdentity pokemon={own} /><div className="versus-chip">对位</div><PokemonIdentity pokemon={rival} align="right" /></div>
          <MatchupStrip own={own} rival={rival} ownDetail={ownDetail} rivalDetail={detail} />
          <VerdictStack own={own} rival={rival} />
        </div>
        <aside className="decision-panel">
          <div className="decision-kicker"><span>本回合重点</span><strong>01</strong></div>
          <h2>先核对实际速度条件</h2>
          <p>{rival.name} 的基础速度为 {rival.speed}，{own.name} 为 {own.speed}。伤害页会采用预存培养、性格、特性、道具与四招，并允许调整全局场况。</p>
          <div className="condition-row"><span>双打</span><span>50 级</span><span>本地规则引擎</span></div>
          <div className="decision-damage"><div><span>当前资料</span>{rival.types.map(type => <TypeBadge key={type} type={type} />)}</div><p>{detail ? `已加载 ${detail.moves.length} 项招式与属性相性。` : '正在读取本地资料…'}</p></div>
          <button className="button primary full" type="button" onClick={onOpenDamage}>用真实规则计算 <ChevronRight size={18} /></button>
          <button className="text-button" type="button" onClick={() => setConditionsOpen(true)}>查看当前计算口径</button>
        </aside>
      </section>

      <section className="intel-panel">
        <div className="tab-list" role="tablist" aria-label="对位资料">{([['summary', '对位结论'], ['moves', '常用招式'], ['types', '属性与形态']] as const).map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}</div>
        <div className="tab-content" role="tabpanel">
          {tab === 'summary' && <SummaryTab own={own} rival={rival} detail={detail} />}
          {tab === 'moves' && <MoveTab moves={detail?.moves ?? []} />}
          {tab === 'types' && <TypeTab rival={rival} detail={detail} />}
        </div>
      </section>
    </div>
  )
}

function SummaryTab({ own, rival, detail }: { own: Pokemon; rival: Pokemon; detail: PokemonDetail | null }) {
  const weakness = detail?.matchups.weakness[0]
  return <div className="summary-grid"><article><span className="summary-number">{weakness ? `${weakness.multiplier}×` : '—'}</span><div><small>主要弱点</small><h3>{weakness?.type ?? '资料读取中'}</h3><p>仅表示属性相性；特性、道具与场况需在计算页确认。</p></div></article><article><span className="summary-number">{own.speed > rival.speed ? '先' : '后'}</span><div><small>基础速度</small><h3>{own.speed > rival.speed ? '我方较快' : '对手较快'}</h3><p>{own.name} {own.speed} / {rival.name} {rival.speed}</p></div></article><article><span className="summary-number">{detail?.moves.length ?? 0}</span><div><small>资料招式</small><h3>当前可用招式池</h3><p>{detail?.notice ?? '正在读取本地采用率快照。'}</p></div></article></div>
}

function MoveTab({ moves: liveMoves }: { moves: Move[] }) {
  const [query, setQuery] = useState('')
  const visible = liveMoves.filter(move => move.name.includes(query.trim())).slice(0, 12)
  return <div className="move-list"><div className="move-list-head"><span>本地资料中的可用招式</span><label><Search size={16} /><input aria-label="搜索招式" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索招式" /></label></div>{visible.map(move => <article key={move.id ?? move.name}><div className="move-main"><strong>{move.name}</strong><TypeBadge type={move.type} /><span>{move.category}</span></div><div className="usage"><span style={{ width: `${move.usage ?? 0}%` }} /><b>{move.usage === null ? '—' : `${move.usage}%`}</b></div><small>{move.description}</small></article>)}{!visible.length && <div className="empty-row">没有匹配的招式资料</div>}</div>
}

function TypeTab({ rival, detail }: { rival: Pokemon; detail: PokemonDetail | null }) {
  return <div className="type-groups"><div><small>当前属性</small><h3>{rival.name}</h3><div className="type-row">{rival.types.map(type => <TypeBadge key={type} type={type} />)}</div></div><div><small>弱点</small><h3>属性倍率</h3><div className="type-row">{detail?.matchups.weakness.map(row => <span className="matchup-tag" key={row.type}><TypeBadge type={row.type} />{row.multiplier}×</span>)}</div></div><div><small>可切换形态</small><h3>{detail?.forms.length ?? 0} 个</h3><p>{detail?.forms.map(form => form.name).join('、') || '无其他形态'}</p></div></div>
}
