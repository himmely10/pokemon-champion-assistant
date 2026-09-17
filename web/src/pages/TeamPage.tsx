import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Copy, ImagePlus, Plus, Save, Search, Trash2 } from 'lucide-react'
import { api } from '../api'
import type { AppSettings, Pokemon, Team, TeamMember, TeamOptions } from '../model'
import { PokemonSlot, TypeBadge } from '../components/BattleComponents'
import { TeamImportPanel } from './TeamImportPanel'

const statFields = [['hp', 'HP'], ['attack', '攻击'], ['defense', '防御'], ['special_attack', '特攻'], ['special_defense', '特防'], ['speed', '速度']] as const

function blankMember(pokemon: Pokemon): TeamMember {
  return { identity: pokemon.id, points: { hp: null, attack: null, defense: null, special_attack: null, special_defense: null, speed: null }, nature: null, ability: null, item: null, moves: [null, null, null, null], pokemon }
}

export function TeamPage({ teams, featured, selectedTeamId, settings, onSelectedTeam, onRefresh, onPendingChange }: {
  teams: Team[]
  featured: Pokemon[]
  selectedTeamId: string | null
  settings: AppSettings
  onSelectedTeam: (id: string) => void
  onRefresh: (preferredId?: string) => Promise<void>
  onPendingChange: (pending: boolean) => void
}) {
  const selectedTeam = teams.find(team => team.id === selectedTeamId) ?? teams[0]
  const [draft, setDraft] = useState<Team | null>(selectedTeam ? structuredClone(selectedTeam) : null)
  const [selected, setSelected] = useState(0)
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<TeamOptions | null>(null)
  const [pokemonChoices, setPokemonChoices] = useState<Pokemon[]>(featured)
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importedDraft, setImportedDraft] = useState(false)
  const draftMode = useRef(false)

  useEffect(() => { onPendingChange(dirty || importOpen) }, [dirty, importOpen, onPendingChange])

  useEffect(() => {
    if (!selectedTeam || draftMode.current) return
    // The editor intentionally resets when the user selects another persisted team.
    // oxlint-disable-next-line react/set-state-in-effect
    setDraft(structuredClone(selectedTeam))
    setSelected(0)
    setDirty(false)
    setMessage('')
  }, [selectedTeam])

  const member = draft?.members[selected]
  useEffect(() => {
    const identity = member?.identity
    if (!identity) return
    let active = true
    // oxlint-disable-next-line react/set-state-in-effect
    setOptions(null)
    api.teamOptions(identity).then(value => { if (active) setOptions(value) }).catch(() => { if (active) setOptions(null) })
    return () => { active = false }
  }, [member?.identity])

  useEffect(() => {
    api.searchPokemon('', 500).then(setPokemonChoices).catch(() => undefined)
  }, [])

  const visibleTeams = useMemo(() => teams.filter(team => team.name.includes(query.trim())), [query, teams])
  const effort = member ? Object.values(member.points).reduce<number>((sum, value) => sum + (value ?? 0), 0) : 0

  const updateMember = (change: Partial<TeamMember>) => {
    if (!draft || saving) return
    const members = draft.members.map((item, index) => index === selected ? { ...item, ...change } : item)
    setDraft({ ...draft, members })
    setDirty(true)
  }

  const save = async () => {
    if (!draft || saving) return
    setSaving(true)
    setMessage('')
    try {
      const saved = await api.saveTeam({ ...draft, registration: draft.members.length === 6 ? 'full' : 'partial' })
      draftMode.current = false
      setDraft(saved)
      setDirty(false)
      setImportedDraft(false)
      try {
        await onRefresh(saved.id)
        setMessage('队伍已经写入本地数据库。')
      } catch {
        setMessage('队伍已保存，但列表刷新失败；请重新打开队伍页面。')
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const confirmDiscard = () => !saving && (!dirty && !importOpen || window.confirm('当前有未保存的导入或编辑内容，确定放弃吗？'))

  const createTeam = () => {
    if (!confirmDiscard()) return
    const pokemon = featured[0]
    if (!pokemon) return
    setDraft({ id: '', revision: 0, name: '新队伍', registration: 'partial', members: [blankMember(pokemon)] })
    draftMode.current = true
    setSelected(0)
    setDirty(true)
    setImportedDraft(false)
    setImportOpen(false)
    setMessage('请补全成员配置后保存。')
  }

  const duplicate = () => {
    if (!draft) return
    if (!confirmDiscard()) return
    setDraft({ ...structuredClone(draft), id: '', revision: 0, name: `${draft.name} 副本` })
    draftMode.current = true
    setDirty(true)
    setImportedDraft(false)
    setImportOpen(false)
    setMessage('已建立副本，保存后才会写入数据库。')
  }

  const removeTeam = async () => {
    if (!draft?.id || importedDraft || saving || !window.confirm(`确定删除队伍“${draft.name}”吗？`)) return
    try {
      await api.deleteTeam(draft)
      await onRefresh()
      setMessage('队伍已删除。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '删除失败')
    }
  }

  const addMember = () => {
    if (!draft || saving || draft.members.length >= 6) return
    const used = new Set(draft.members.map(item => item.identity))
    const pokemon = pokemonChoices.find(item => !used.has(item.id))
    if (!pokemon) return
    setDraft({ ...draft, members: [...draft.members, blankMember(pokemon)] })
    setSelected(draft.members.length)
    setDirty(true)
  }

  const selectPersistedTeam = (team: Team) => {
    if (!confirmDiscard()) return
    setImportOpen(false)
    setImportedDraft(false)
    draftMode.current = false
    setDraft(structuredClone(team))
    setSelected(0)
    setDirty(false)
    onSelectedTeam(team.id)
  }

  const loadImportedDraft = (next: Team, notice: string) => {
    if (saving) return
    setDraft({ ...next, id: '', revision: 0 })
    draftMode.current = true
    setSelected(0)
    setDirty(true)
    setImportedDraft(true)
    setImportOpen(false)
    setMessage(notice || '截图草稿已载入，请核对后保存。')
  }

  const importAction = <button className="button secondary" type="button" disabled={saving} onClick={() => { if (confirmDiscard()) setImportOpen(true) }}><ImagePlus size={17} />截图导入队伍</button>

  if (!draft || !member) {
    return <div className="standard-page team-page"><section className="page-toolbar"><div><p className="eyebrow">队伍配置</p><h2>管理你的预存队伍</h2></div><div className="toolbar-actions">{importAction}<button className="button primary" type="button" onClick={createTeam}><Plus size={17} />创建队伍</button></div></section>{importOpen && <TeamImportPanel settings={settings} onDraft={loadImportedDraft} onCancel={() => { if (confirmDiscard()) setImportOpen(false) }} />}<div className="empty-battle"><h2>还没有预存队伍</h2><p>可从游戏的能力页和状态页截图导入，或手动创建。</p></div></div>
  }

  const pokemon = member.pokemon ?? options?.pokemon
  return <div className="standard-page team-page">
    <section className="page-toolbar"><div><p className="eyebrow">队伍配置</p><h2>管理你的预存队伍</h2><p>这里保存的培养、特性、道具和招式会继续由原有规则校验。</p></div><div className="toolbar-actions">{importAction}<button className="button quiet" type="button" onClick={duplicate}><Copy size={17} />复制当前队伍</button><button className="button primary" type="button" onClick={createTeam}><Plus size={17} />创建队伍</button></div></section>

    {importOpen && <TeamImportPanel settings={settings} onDraft={loadImportedDraft} onCancel={() => { if (confirmDiscard()) setImportOpen(false) }} />}

    <section className="team-workspace">
      <aside className="team-list-panel">
        <label className="search-field"><Search size={17} /><input aria-label="搜索队伍" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索队伍" /></label>
        <h3>本地队伍</h3>
        {visibleTeams.map(team => <button key={team.id} type="button" disabled={saving} className={!importedDraft && team.id === selectedTeam?.id ? 'active' : ''} onClick={() => selectPersistedTeam(team)}><span className="team-color" /><span><strong>{team.name}</strong><small>{team.members.length}/6 · {team.registration === 'full' ? '完整登记' : '部分登记'}</small></span>{!importedDraft && team.id === selectedTeamId && <Check size={16} />}</button>)}
      </aside>

      <div className="team-editor">
        <div className="team-editor-head"><span className={`saved-state ${dirty ? 'warning' : ''}`}><Check size={15} />{importedDraft ? '未保存的导入队伍' : dirty ? '有未保存更改' : '所有更改已保存'}</span><input className="team-name-input" value={draft.name} disabled={saving} aria-label="队伍名称" onChange={event => { setDraft({ ...draft, name: event.target.value }); setDirty(true) }} /><div className="team-editor-actions"><button className="icon-button" type="button" disabled={saving} onClick={duplicate} aria-label="复制队伍" title="复制队伍"><Copy size={18} /></button>{draft.id && !importedDraft && <button className="icon-button danger" type="button" disabled={saving} onClick={() => void removeTeam()} aria-label="删除队伍" title="删除队伍"><Trash2 size={18} /></button>}</div></div>
        <fieldset className="member-strip" disabled={saving}><legend className="sr-only">队伍成员</legend>{draft.members.map((item, index) => item.pokemon && <PokemonSlot key={`${item.identity}-${index}`} pokemon={item.pokemon} side="own" selected={selected === index} onSelect={() => setSelected(index)} />)}{draft.members.length < 6 && <button className="add-member-slot" type="button" onClick={addMember}><Plus size={18} />添加成员</button>}</fieldset>

        {pokemon && <div className="member-title"><div><img src={pokemon.image} alt={`宝可梦：${pokemon.name}`} /><div><small>成员 {selected + 1}</small><h2>{pokemon.name}</h2><div className="type-row">{pokemon.types.map(type => <TypeBadge type={type} key={type} />)}</div></div></div><span className="complete-pill">{options ? '可编辑' : '读取配置中'}</span></div>}

        <form className="config-form" onSubmit={event => { event.preventDefault(); void save() }}>
          <fieldset disabled={saving}><legend>身份</legend><label><span>宝可梦 / 形态</span><select value={member.identity} onChange={event => { const next = pokemonChoices.find(item => item.id === event.target.value); if (next) updateMember(blankMember(next)) }}><option value={member.identity}>{pokemon?.name ?? member.identity}</option>{pokemonChoices.filter(item => item.id !== member.identity).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></fieldset>
          <fieldset><legend>培养</legend><div className="effort-summary"><span>已分配培养点</span><strong>{effort} / {options?.point_rules.total ?? 66}</strong><div><i style={{ width: `${Math.min(100, effort / (options?.point_rules.total ?? 66) * 100)}%` }} /></div></div><div className="form-grid stats-grid">{statFields.map(([key, label]) => <label key={key}><span>{label}</span><input type="number" min="0" max={options?.point_rules.per_stat ?? 32} value={member.points[key] ?? ''} placeholder="未知" onChange={event => updateMember({ points: { ...member.points, [key]: event.target.value === '' ? null : Number(event.target.value) } })} /></label>)}</div><div className="form-grid"><label><span>性格</span><select value={member.nature ?? ''} onChange={event => updateMember({ nature: event.target.value || null })}><option value="">未知</option>{options?.natures.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>特性</span><select value={member.ability ?? ''} onChange={event => updateMember({ ability: event.target.value || null })}><option value="">未知</option>{options?.abilities.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>道具</span><select value={member.item ?? ''} onChange={event => updateMember({ item: event.target.value || null })}><option value="">未知</option>{options?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div></fieldset>
          <fieldset><legend>招式</legend><div className="form-grid move-grid">{member.moves.map((move, index) => <label key={index}><span>招式 {index + 1}</span><select value={move ?? ''} onChange={event => { const moves = [...member.moves]; moves[index] = event.target.value || null; updateMember({ moves }) }}><option value="">未知</option>{options?.moves.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>)}</div></fieldset>
        </form>
        <div className="sticky-save"><button className="button danger ghost" type="button" disabled={saving || draft.members.length <= 1} onClick={() => { const members = draft.members.filter((_, index) => index !== selected); setDraft({ ...draft, members }); setSelected(Math.max(0, selected - 1)); setDirty(true) }}><Trash2 size={17} />删除这名成员</button><div className="save-actions">{message && <span className="form-message">{message}</span>}<button className="button primary" type="button" disabled={!dirty || saving} onClick={() => void save()}><Save size={17} />{saving ? '保存中…' : dirty ? '保存队伍' : '已保存'}</button></div></div>
      </div>
    </section>
  </div>
}
