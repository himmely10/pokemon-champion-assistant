import { Fragment, useEffect, useMemo, useState } from 'react'
import { Calculator, ChevronDown, CircleHelp, Gauge, RotateCw, Shield, SlidersHorizontal, Zap } from 'lucide-react'
import { api } from '../api'
import type { AbilityOption, BattleState, DamageOptions, DamageResponse, Pokemon, PokemonDetail, Team, TeamMember } from '../model'
import { DamageBar, MatchupStrip, PokemonIdentity, TypeBadge } from '../components/BattleComponents'

const BOOSTS = [
  ['attack', '攻击'], ['defense', '防御'], ['special_attack', '特攻'],
  ['special_defense', '特防'], ['speed', '速度'],
] as const

const WEATHER = [
  ['', '无天气'], ['Sun', '晴天'], ['Rain', '雨天'], ['Sand', '沙暴'], ['Snow', '雪天'],
] as const

const TERRAIN = [
  ['', '无场地'], ['Electric', '电气场地'], ['Grassy', '青草场地'],
  ['Misty', '薄雾场地'], ['Psychic', '精神场地'],
] as const

const blankBattle = (): BattleState => ({
  hp: 100,
  status: '',
  allies_fainted: 0,
  boosts: { attack: 0, defense: 0, special_attack: 0, special_defense: 0, speed: 0 },
  ability_on: false,
  reflect: false,
  light_screen: false,
  protected: false,
  helping_hand: false,
  friend_guard: false,
  tailwind: false,
  aurora_veil: false,
  charge_boost_included: false,
})

type DamagePageProps = {
  teams: Team[]
  selectedTeamId: string | null
  onTeamChange: (id: string) => void
  own: Pokemon
  ownMember?: TeamMember
  ownTeam: Pokemon[]
  onOwnChange: (id: string) => void
  rival: Pokemon
  rivalTeam: Pokemon[]
  onRivalChange: (id: string) => void
}

export function DamagePage({ teams, selectedTeamId, onTeamChange, own, ownMember, ownTeam, onOwnChange, rival, rivalTeam, onRivalChange }: DamagePageProps) {
  const [direction, setDirection] = useState<'own' | 'rival' | 'field'>('own')
  const [selectedMove, setSelectedMove] = useState<number | null>(null)
  const [selectedScenarios, setSelectedScenarios] = useState({ own: 0, rival: 0 })
  const [weather, setWeather] = useState('')
  const [terrain, setTerrain] = useState('')
  const [targets, setTargets] = useState(2)
  const [critical, setCritical] = useState(false)
  const [ownFormId, setOwnFormId] = useState(own.id)
  const [rivalFormId, setRivalFormId] = useState(rival.id)
  const [ownAbility, setOwnAbility] = useState(ownMember?.ability ?? '__none__')
  const [rivalAbility, setRivalAbility] = useState('__none__')
  const [copiedAbility, setCopiedAbility] = useState('__none__')
  const [ownBattle, setOwnBattle] = useState<BattleState>(blankBattle)
  const [rivalBattle, setRivalBattle] = useState<BattleState>(blankBattle)
  const [ownOptions, setOwnOptions] = useState<DamageOptions | null>(null)
  const [rivalOptions, setRivalOptions] = useState<DamageOptions | null>(null)
  const [ownDetail, setOwnDetail] = useState<PokemonDetail | null>(null)
  const [rivalDetail, setRivalDetail] = useState<PokemonDetail | null>(null)
  const [result, setResult] = useState<DamageResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let current = true
    Promise.all([api.damageOptions(ownFormId), api.pokemonDetail(ownFormId)]).then(([options, detail]) => {
      if (!current) return
      setOwnOptions(options)
      setOwnDetail(detail)
      setOwnAbility(value => options.abilities.some(item => item.id === value) ? value : options.abilities[0]?.id ?? '__none__')
    }).catch(() => current && setOwnDetail(null))
    return () => { current = false }
  }, [ownFormId])

  useEffect(() => {
    let current = true
    Promise.all([api.damageOptions(rivalFormId), api.pokemonDetail(rivalFormId)]).then(([options, detail]) => {
      if (!current) return
      setRivalOptions(options)
      setRivalDetail(detail)
      setRivalAbility(value => options.abilities.some(item => item.id === value) || value === '__none__'
        ? (options.abilities.length === 1 ? options.abilities[0].id : value)
        : '__none__')
    }).catch(() => current && setRivalDetail(null))
    return () => { current = false }
  }, [rivalFormId])

  useEffect(() => {
    let current = true
    // Initial calculation synchronizes this freshly mounted matchup with the local rules service.
    // oxlint-disable-next-line react/set-state-in-effect
    setLoading(true)
    setError('')
    void api.damage(own.id, rival.id, {
      environment: { weather: '', terrain: '', targets: 2, critical: false },
      ownMember,
    }).then(value => {
      if (current) setResult(value)
    }).catch(reason => {
      if (current) setError(reason instanceof Error ? reason.message : '计算失败')
    }).finally(() => {
      if (current) setLoading(false)
    })
    return () => { current = false }
  }, [own, ownMember, rival])

  const calculate = async () => {
    setLoading(true)
    setError('')
    try {
      const value = await api.damage(own.id, rival.id, {
        environment: { weather, terrain, targets, critical },
        ownMember,
        ownFormId,
        rivalFormId,
        ownAbility,
        rivalAbility,
        copiedAbility,
        ownBattle,
        rivalBattle,
      })
      setResult(value)
      setSelectedMove(null)
      setSelectedScenarios({ own: 0, rival: 0 })
      setDirty(false)
    } catch (reason) {
      setResult(null)
      setError(reason instanceof Error ? reason.message : '计算失败')
    } finally {
      setLoading(false)
    }
  }

  const displayedOwn = ownOptions?.forms.find(item => item.id === ownFormId) ?? own
  const displayedRival = rivalOptions?.forms.find(item => item.id === rivalFormId) ?? rival
  const activeScenarios = direction === 'rival' ? result?.rival_scenarios : result?.own_scenarios
  const activeScenarioIndex = direction === 'rival' ? selectedScenarios.rival : selectedScenarios.own
  const active = activeScenarios?.[activeScenarioIndex] ?? (direction === 'rival' ? result?.rival : result?.own)
  const displayed = active?.moves ?? []
  const ownAbilityOption = ownOptions?.abilities.find(item => item.id === ownAbility)
  const rivalAbilityOption = rivalOptions?.abilities.find(item => item.id === rivalAbility)
  const rivalChoices = useMemo(() => {
    const groups = new Map<string, { base: Pokemon; source: Pokemon }>()
    for (const pokemon of rivalTeam) {
      const base = pokemon.id === pokemon.family_base.id
        ? pokemon
        : { ...pokemon, ...pokemon.family_base, family_base: pokemon.family_base, is_battle_form: false }
      const current = groups.get(base.id)
      if (!current || pokemon.id === base.id) groups.set(base.id, { base, source: pokemon })
    }
    return [...groups.values()]
  }, [rivalTeam])
  const selectedRivalChoice = rivalChoices.find(choice => choice.base.id === rival.family_base.id)

  const markDirty = () => setDirty(true)
  const updateWeather = (value: string) => {
    setWeather(value)
    const sync = (state: BattleState, ability: AbilityOption | undefined) => ability?.scene_requirement?.kind === 'weather'
      ? { ...state, ability_on: ability.scene_requirement.value === value }
      : state
    setOwnBattle(state => sync(state, ownAbilityOption))
    setRivalBattle(state => sync(state, rivalAbilityOption))
    markDirty()
  }
  const updateTerrain = (value: string) => {
    setTerrain(value)
    const sync = (state: BattleState, ability: AbilityOption | undefined) => ability?.scene_requirement?.kind === 'terrain'
      ? { ...state, ability_on: ability.scene_requirement.value === value }
      : state
    setOwnBattle(state => sync(state, ownAbilityOption))
    setRivalBattle(state => sync(state, rivalAbilityOption))
    markDirty()
  }
  const changeAbility = (side: 'own' | 'rival', value: string) => {
    const options = side === 'own' ? ownOptions : rivalOptions
    const ability = options?.abilities.find(item => item.id === value)
    const automatic = ability?.scene_requirement?.kind === 'weather'
      ? ability.scene_requirement.value === weather
      : ability?.scene_requirement?.kind === 'terrain'
        ? ability.scene_requirement.value === terrain
        : ability?.hp_requirement === 'full'
    if (side === 'own') {
      setOwnAbility(value)
      setOwnBattle(state => ({ ...state, ability_on: Boolean(automatic) }))
    } else {
      setRivalAbility(value)
      setRivalBattle(state => ({ ...state, ability_on: Boolean(automatic) }))
    }
    markDirty()
  }
  const triggerAbility = (side: 'own' | 'rival', checked: boolean) => {
    const ability = side === 'own' ? ownAbilityOption : rivalAbilityOption
    const setBattle = side === 'own' ? setOwnBattle : setRivalBattle
    setBattle(state => ({ ...state, ability_on: checked, ...(checked && ability?.hp_requirement === 'full' ? { hp: 100 } : {}) }))
    if (checked && ability?.scene_requirement?.kind === 'weather') setWeather(ability.scene_requirement.value)
    if (checked && ability?.scene_requirement?.kind === 'terrain') setTerrain(ability.scene_requirement.value)
    markDirty()
  }
  const changeForm = (side: 'own' | 'rival', value: string) => {
    const options = side === 'own' ? ownOptions : rivalOptions
    const form = options?.forms.find(item => item.id === value)
    const nextAbility = form?.abilities.length === 1
      ? form.abilities[0].id
      : side === 'own' && value === own.id && ownMember?.ability && form?.abilities.some(item => item.id === ownMember.ability)
        ? ownMember.ability
        : '__none__'
    if (side === 'own') {
      setOwnFormId(value)
      setOwnAbility(nextAbility)
      setOwnBattle(state => ({ ...state, ability_on: false }))
    } else {
      setRivalFormId(value)
      setRivalAbility(nextAbility)
      setRivalBattle(state => ({ ...state, ability_on: false }))
    }
    setResult(null)
    setError('')
    markDirty()
  }

  return <div className="standard-page damage-page">
    <section className="damage-selector-bar" aria-label="伤害计算对位选择">
      <label><span>我方队伍</span><select value={selectedTeamId ?? ''} onChange={event => onTeamChange(event.target.value)}>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>
      <label><span>我方宝可梦</span><select value={own.id} onChange={event => onOwnChange(event.target.value)}>{ownTeam.map(pokemon => <option key={pokemon.id} value={pokemon.id}>{pokemon.name}</option>)}</select></label>
      <label><span>我方战斗形态</span><select value={ownFormId} onChange={event => changeForm('own', event.target.value)}>{(ownOptions?.forms ?? [own]).map(form => <option key={form.id} value={form.id}>{form.name}</option>)}</select></label>
      <span className="selector-versus">VS</span>
      <label><span>对手宝可梦</span><select value={selectedRivalChoice?.source.id ?? rival.id} onChange={event => onRivalChange(event.target.value)}>{rivalChoices.map(choice => <option key={choice.base.id} value={choice.source.id}>{choice.base.name}</option>)}</select></label>
      <label><span>对手战斗形态</span><select value={rivalFormId} onChange={event => changeForm('rival', event.target.value)}>{(rivalOptions?.forms ?? [rival]).map(form => <option key={form.id} value={form.id}>{form.name}</option>)}</select></label>
    </section>

    <section className="damage-header">
      <div className="battle-pair"><PokemonIdentity pokemon={displayedOwn} /><span className="versus-chip">对位</span><PokemonIdentity pokemon={displayedRival} align="right" /></div>
      <div className="damage-header-actions"><span className={`sync-badge ${error ? 'error' : dirty ? 'pending' : ''}`}><RotateCw size={15} />{loading ? '规则引擎计算中' : error || (dirty ? '条件已修改，等待重新计算' : '已与当前条件同步')}</span><button className="button primary" type="button" onClick={() => void calculate()} disabled={loading}><Calculator size={17} />重新计算</button></div>
    </section>

    <MatchupStrip own={displayedOwn} rival={displayedRival} ownDetail={ownDetail} rivalDetail={rivalDetail} />

    <section className="condition-panel advanced-conditions">
      <div className="global-condition-block"><div className="condition-heading"><div><small>规则与目标</small><h3>全局场况</h3></div><SlidersHorizontal size={18} /></div><div className="condition-controls"><label><span>有效目标数</span><select value={targets} onChange={event => { setTargets(Number(event.target.value)); markDirty() }}><option value={2}>双打范围招式</option><option value={1}>单目标</option></select></label><label><span>天气</span><select value={weather} onChange={event => updateWeather(event.target.value)}>{WEATHER.map(([id, name]) => <option key={id || 'none'} value={id}>{name}</option>)}</select></label><label><span>场地</span><select value={terrain} onChange={event => updateTerrain(event.target.value)}>{TERRAIN.map(([id, name]) => <option key={id || 'none'} value={id}>{name}</option>)}</select></label><label className="check-control"><input type="checkbox" checked={critical} onChange={event => { setCritical(event.target.checked); markDirty() }} /><span>必定要害</span></label></div></div>
      <BattleStatePanel side="own" pokemon={displayedOwn} state={ownBattle} onState={value => { setOwnBattle(value); markDirty() }} abilities={ownOptions?.abilities ?? []} ability={ownAbility} onAbility={value => changeAbility('own', value)} onTrigger={checked => triggerAbility('own', checked)} supportEffects={ownOptions?.support_effects ?? []} statuses={ownOptions?.statuses ?? []} />
      <BattleStatePanel side="rival" pokemon={displayedRival} state={rivalBattle} onState={value => { setRivalBattle(value); markDirty() }} abilities={rivalOptions?.abilities ?? []} ability={rivalAbility} onAbility={value => changeAbility('rival', value)} onTrigger={checked => triggerAbility('rival', checked)} supportEffects={rivalOptions?.support_effects ?? []} statuses={rivalOptions?.statuses ?? []} />
      {ownAbility === 'trace' && <label className="copied-ability"><span>复制实际获得的特性</span><select value={copiedAbility} onChange={event => { setCopiedAbility(event.target.value); markDirty() }}><option value="__none__">未触发／无特性效果</option>{ownOptions?.copiable_abilities.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <button className="button secondary apply-conditions" type="button" onClick={() => void calculate()} disabled={loading}><SlidersHorizontal size={17} />应用全部条件</button>
    </section>

    <SpeedComparison result={result} ownName={displayedOwn.name} rivalName={displayedRival.name} />

    <section className="calculation-panel">
      <div className="direction-tabs" role="tablist" aria-label="计算方向"><button type="button" role="tab" aria-selected={direction === 'own'} className={direction === 'own' ? 'active' : ''} onClick={() => { setDirection('own'); setSelectedMove(null) }}>我方打对手</button><button type="button" role="tab" aria-selected={direction === 'rival'} className={direction === 'rival' ? 'active' : ''} onClick={() => { setDirection('rival'); setSelectedMove(null) }}>对手打我方</button><button type="button" role="tab" aria-selected={direction === 'field'} className={direction === 'field' ? 'active' : ''} onClick={() => { setDirection('field'); setSelectedMove(null) }}>计算口径</button></div>
      {direction === 'field' ? <CalculationScope result={result} weather={weather} terrain={terrain} ownBattle={ownBattle} rivalBattle={rivalBattle} /> : <>
        <ScenarioSelector direction={direction} scenarios={activeScenarios ?? []} selected={activeScenarioIndex} onSelect={index => { setSelectedScenarios(value => ({ ...value, [direction]: index })); setSelectedMove(null) }} />
        <div className="calculation-intro"><div><small>即时计算</small><h2>{active?.attacker.name ?? '正在准备'} 的招式</h2></div><div className="active-conditions"><span>{active?.preset ?? '预存配置'}</span><span>{active?.target_preset ?? '对手假设'}</span><span>{active?.speed.status === 'ok' ? `实算速度 ${active.speed.speed}` : '速度不可用'}</span></div></div>
        {loading && <div className="calculation-loading"><span className="spinner" />正在运行本地伤害引擎…</div>}
        {!loading && error && <div className="calculation-error">{error}</div>}
        {!loading && !error && <div className="damage-table" aria-label="伤害计算结果">
          <div className="damage-table-head"><span>招式</span><span>伤害范围</span><span>命中 / 先制</span><span>威力</span><span>击杀判断</span></div>
          {displayed.map((item, index) => {
            const expanded = selectedMove === index
            const detailId = `move-detail-${direction}-${index}`
            return <Fragment key={`${item.id ?? item.name}-${index}`}><button type="button" aria-label={`${expanded ? '收起' : '展开'}${item.name}的计算详情`} aria-expanded={expanded} aria-controls={detailId} className={expanded ? 'selected' : ''} onClick={() => setSelectedMove(current => current === index ? null : index)}><span className="damage-move"><strong>{item.name}</strong><TypeBadge type={item.type} /></span>{item.damage ? <DamageBar move={item} side={direction} /> : <span className="unavailable-result">{item.reason ?? '不可计算'}</span>}<span className="move-order"><b>{item.hit_chance?.percent == null ? '命中 —' : `命中 ${item.hit_chance.percent}%`}</b><small>{item.priority?.current == null ? '先制 —' : `先制 ${item.priority.current >= 0 ? '+' : ''}${item.priority.current}`}</small></span><span className="power-cell">{item.power ?? '—'}</span><span className="verdict-cell">{item.verdict ?? (item.category === '变化' ? '变化招式' : '不可用')}<ChevronDown className={`detail-chevron ${expanded ? 'expanded' : ''}`} size={16} /></span></button>{expanded && <MoveDetail id={detailId} move={item} dataset={result?.dataset_id} />}</Fragment>
          })}
        </div>}
      </>}
    </section>
  </div>
}

function ScenarioSelector({ direction, scenarios, selected, onSelect }: {
  direction: 'own' | 'rival'
  scenarios: DamageResponse['own_scenarios']
  selected: number
  onSelect: (index: number) => void
}) {
  const groups = [
    { label: direction === 'own' ? '基准耐久' : '基准输出', items: scenarios.slice(0, 3), offset: 0 },
    { label: '常用分配', items: scenarios.slice(3), offset: 3 },
  ]
  const points = (scenario: DamageResponse['own_scenarios'][number]) => Object.entries(scenario.scenario_points ?? {})
    .filter(([, value]) => Boolean(value))
    .map(([key, value]) => `${{ hp: 'HP', attack: '攻击', defense: '防御', special_attack: '特攻', special_defense: '特防', speed: '速度' }[key as keyof TeamMember['points']]} ${value}`)
    .join(' / ') || '无培养点'
  return <div className="scenario-groups" aria-label={direction === 'own' ? '对手耐久情景' : '对手输出情景'}>
    {groups.map(group => group.items.length > 0 && <div className="scenario-group" key={group.label}><span>{group.label}</span><div role="tablist" aria-label={group.label}>{group.items.map((scenario, index) => {
      const absolute = group.offset + index
      const label = direction === 'own' ? scenario.target_preset : scenario.preset
      return <button type="button" role="tab" aria-selected={selected === absolute} className={selected === absolute ? 'active' : ''} key={`${label}-${absolute}`} title={`${scenario.scenario_nature ?? '未知性格'}；${points(scenario)}`} onClick={() => onSelect(absolute)}><strong>{label}</strong><small>{scenario.spread_usage != null ? `采用率 ${scenario.spread_usage}%` : scenario.scenario_nature}</small></button>
    })}</div></div>)}
  </div>
}

function BattleStatePanel({ side, pokemon, state, onState, abilities, ability, onAbility, onTrigger, supportEffects, statuses }: {
  side: 'own' | 'rival'
  pokemon: Pokemon
  state: BattleState
  onState: (value: BattleState) => void
  abilities: AbilityOption[]
  ability: string
  onAbility: (value: string) => void
  onTrigger: (checked: boolean) => void
  supportEffects: DamageOptions['support_effects']
  statuses: DamageOptions['statuses']
}) {
  const selectedAbility = abilities.find(item => item.id === ability)
  const update = <K extends keyof BattleState,>(key: K, value: BattleState[K]) => onState({ ...state, [key]: value })
  const groups = useMemo(() => Array.from(new Set(supportEffects.map(item => item.group))), [supportEffects])
  return <div className={`battle-state-panel ${side}`}>
    <div className="condition-heading"><div><small>{side === 'own' ? '我方状态' : '对手状态'}</small><h3>{pokemon.name}</h3></div><span className="side-dot" /></div>
    <div className="battle-state-primary">
      <label><span>本次计算特性</span><select value={ability} onChange={event => onAbility(event.target.value)} disabled={abilities.length === 1}>{abilities.length !== 1 && <option value="__none__">无特性效果（假设）</option>}{abilities.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>当前 HP %</span><input type="number" min={1} max={100} value={state.hp} onChange={event => { const hp = Number(event.target.value); onState({ ...state, hp, ability_on: selectedAbility?.hp_requirement === 'full' ? hp === 100 : state.ability_on }) }} /><small>100 表示满 HP</small></label>
      <label><span>异常状态</span><select value={state.status} onChange={event => update('status', event.target.value)}>{statuses.map(item => <option key={item.id || 'none'} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>倒下同伴</span><select value={state.allies_fainted} onChange={event => update('allies_fainted', Number(event.target.value))}>{[0, 1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
    </div>
    {selectedAbility?.description && <p className="ability-description"><Zap size={14} />{selectedAbility.name}：{selectedAbility.description}</p>}
    {selectedAbility?.trigger_label && <label className="ability-trigger"><input type="checkbox" checked={state.ability_on} onChange={event => onTrigger(event.target.checked)} /><span>{selectedAbility.trigger_label}</span></label>}
    <div className="support-groups always-visible">{groups.map(group => <fieldset key={group}><legend>{group}</legend>{supportEffects.filter(effect => effect.group === group).map(effect => <label key={effect.id} title={effect.description}><input type="checkbox" checked={Boolean(state[effect.id])} onChange={event => update(effect.id, event.target.checked)} /><span>{effect.label}</span></label>)}</fieldset>)}</div>
    <details className="battle-state-details" open>
      <summary>能力等级与电光束 <span>{Object.values(state.boosts).filter(Boolean).length + Number(state.charge_boost_included)} 项已调整</span></summary>
      <div className="boost-grid">{BOOSTS.map(([key, name]) => <label key={key}><span>{name}等级</span><select value={state.boosts[key]} onChange={event => onState({ ...state, boosts: { ...state.boosts, [key]: Number(event.target.value) } })}>{Array.from({ length: 13 }, (_, index) => index - 6).map(value => <option key={value} value={value}>{value >= 0 ? `+${value}` : value}</option>)}</select></label>)}</div>
      <label className="charge-control"><input type="checkbox" checked={state.charge_boost_included} onChange={event => update('charge_boost_included', event.target.checked)} /><span>电光束：特攻等级已包含本次充能 +1</span></label>
    </details>
  </div>
}

function SpeedComparison({ result, ownName, rivalName }: { result: DamageResponse | null; ownName: string; rivalName: string }) {
  const comparison = result?.speed_comparison
  return <section className="speed-comparison" aria-labelledby="speed-comparison-title">
    <div className="fixed-speed"><Gauge size={22} /><div><small>我方实配速度 · 固定比较基准</small><h2 id="speed-comparison-title">{comparison?.own.status === 'ok' ? comparison.own.speed : '—'}</h2><span>{ownName}{comparison?.own.raw_speed ? ` · 原始 ${comparison.own.raw_speed}` : ''}</span></div></div>
    <div className="speed-tier-table"><div className="speed-tier-head"><span>{rivalName} 的 50 级参考档位 · 由快到慢</span><span>对手速度</span><span>与我方关系</span></div>{comparison?.tiers.map(tier => <div className={`speed-tier-row ${tier.kind}`} key={`${tier.kind}-${tier.name}`} title={tier.description}><strong>{tier.name}{tier.kind === 'common' && <small>常用{tier.usage != null ? ` ${tier.usage}%` : ''}</small>}</strong><b>{tier.speed}</b><span className={tier.relation === '我方更快' ? 'positive' : tier.relation === '同速' ? 'neutral' : 'negative'}>{tier.relation}</span></div>)}{!comparison?.tiers.length && <div className="speed-unavailable">{comparison?.reason ?? comparison?.own.reason ?? '重新计算后显示速度线'}</div>}</div>
  </section>
}

function MoveDetail({ id, move, dataset }: { id: string; move: DamageResponse['own']['moves'][number]; dataset?: string }) {
  const koChance = move.ko_chance == null ? null : `${Number.isInteger(move.ko_chance) ? move.ko_chance.toFixed(0) : move.ko_chance.toFixed(1)}%`
  return <article id={id} className="calculation-detail expanded"><div className="move-detail-copy"><small>招式详情</small><h3>{move.name}</h3><p>{move.description}</p><div className="move-metrics"><span>{move.damage ? `${move.damage[0]}–${move.damage[1]}%` : '无直接伤害'}</span><span>{move.minimum != null ? `${move.minimum}–${move.maximum} HP` : 'HP 伤害 —'}</span>{koChance && <span className="ko-chance-detail">命中后击杀概率 {koChance}</span>}<span>{move.hit_chance?.percent == null ? '命中 —' : `实际命中 ${move.hit_chance.percent}%`}</span><span>{move.priority?.current == null ? '先制 —' : `当前先制 ${move.priority.current >= 0 ? '+' : ''}${move.priority.current}`}</span></div></div><div className="effect-audit"><small>本招场况判定</small>{move.support_effects?.length ? move.support_effects.map((effect, index) => <div className={`effect-row ${effect.state}`} key={`${effect.key}-${effect.side}-${index}`}><Shield size={14} /><div><strong>{effect.side === 'attackerSide' ? '攻击方' : '防守方'} · {effect.label}</strong><span>{effect.state === 'applied' ? '已生效' : effect.state === 'ignored' ? '本招忽略' : '条件输入'}：{effect.reason}</span></div></div>) : <p>无额外辅助效果；携带辅助招式不会自动视为已生效。</p>}<div className="detail-notes">{move.hit_chance?.notes.map(note => <span key={note}>命中：{note}</span>)}{move.priority?.notes.map(note => <span key={note}>先制：{note}</span>)}{move.current_hp != null && move.max_hp != null && <span>目标当前 HP {move.current_hp} / {move.max_hp}</span>}<span>资料 {dataset?.slice(0, 12) ?? '—'}</span></div></div></article>
}

function CalculationScope({ result, weather, terrain, ownBattle, rivalBattle }: { result: DamageResponse | null; weather: string; terrain: string; ownBattle: BattleState; rivalBattle: BattleState }) {
  const active = (state: BattleState) => [state.helping_hand && '帮助', state.reflect && '反射壁', state.light_screen && '光墙', state.aurora_veil && '极光幕', state.protected && '守住', state.friend_guard && '友情防守', state.tailwind && '顺风'].filter(Boolean).join('、') || '无额外效果'
  return <div className="field-settings"><div><small>本次请求</small><h2>原有 Champions 规则引擎</h2><p>形态、特性、战斗状态和辅助效果都会发送给本地 Python 服务；最终伤害仍由内置规则快照计算。</p><details className="damage-help"><summary><CircleHelp size={16} />查看计算说明</summary><p>属性相性条不包含特性和道具；伤害结果会包含这些修正。帮助只作用于攻击方，反射壁和光墙只作用于防守方；要害、穿透、拆墙和守住穿透由规则引擎逐招判断。对手培养点使用当前显示的独立假设，不代表联合采用率。</p></details></div><div className="field-settings-grid"><label><span>天气 / 场地</span><strong>{WEATHER.find(item => item[0] === weather)?.[1]} / {TERRAIN.find(item => item[0] === terrain)?.[1]}</strong></label><label><span>我方已启用</span><strong>{active(ownBattle)}</strong></label><label><span>对手已启用</span><strong>{active(rivalBattle)}</strong></label><label><span>资料版本</span><strong>{result?.dataset_id ?? '—'}</strong></label></div></div>
}
