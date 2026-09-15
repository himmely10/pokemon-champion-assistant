import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { AppShell } from './components/AppShell'
import { BattlePage } from './pages/BattlePage'
import { DamagePage } from './pages/DamagePage'
import { ReferencePage } from './pages/ReferencePage'
import { SettingsPage } from './pages/SettingsPage'
import { TeamPage } from './pages/TeamPage'
import type { Bootstrap, PageId, Pokemon, RecognitionReport } from './model'

function basePokemon(pokemon: Pokemon): Pokemon {
  if (pokemon.id === pokemon.family_base.id) return pokemon
  return { ...pokemon, ...pokemon.family_base, family_base: pokemon.family_base, is_battle_form: false }
}

function uniqueFamilies(values: Pokemon[]): Pokemon[] {
  const families = new Map<string, Pokemon>()
  for (const pokemon of values) {
    const base = basePokemon(pokemon)
    if (!families.has(base.id)) families.set(base.id, base)
  }
  return [...families.values()]
}

function App() {
  const [page, setPage] = useState<PageId>('battle')
  const [dark, setDark] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [recognition, setRecognition] = useState<RecognitionReport | null>(null)
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null)
  const [ownId, setOwnId] = useState<string | null>(null)
  const [rivalId, setRivalId] = useState<string | null>(null)
  const [startupError, setStartupError] = useState('')

  useEffect(() => {
    api.bootstrap().then(data => {
      setBootstrap(data)
      const teamId = data.settings.selected_team_id ?? data.teams[0]?.id ?? null
      setSelectedTeamId(teamId)
      const team = data.teams.find(item => item.id === teamId) ?? data.teams[0]
      const featuredFamilies = uniqueFamilies(data.featured)
      setOwnId(team?.members[0]?.identity ?? featuredFamilies[0]?.id ?? null)
      setRivalId(featuredFamilies[2]?.id ?? featuredFamilies[0]?.id ?? null)
      setDark(data.settings.theme === 'dark')
      setReducedMotion(data.settings.reduced_motion)
    }).catch(error => setStartupError(error instanceof Error ? error.message : '无法连接本地服务'))
  }, [])

  const selectedTeam = useMemo(() => bootstrap?.teams.find(team => team.id === selectedTeamId) ?? bootstrap?.teams[0] ?? null, [bootstrap, selectedTeamId])
  const ownTeam = useMemo(() => selectedTeam?.members.map(member => member.pokemon).filter(member => member !== null) ?? bootstrap?.featured.slice(0, 6) ?? [], [bootstrap, selectedTeam])
  const rivalTeam = useMemo(() => {
    const recognized = recognition?.opponent.map(slot => slot.pokemon).filter(member => member !== null) ?? []
    return recognized.length ? recognized : uniqueFamilies(bootstrap?.featured ?? []).slice(0, 6)
  }, [bootstrap, recognition])

  const refreshTeams = async (preferredId?: string) => {
    const teams = await api.teams()
    setBootstrap(value => value ? { ...value, teams } : value)
    if (preferredId) setSelectedTeamId(preferredId)
  }

  const selectTeam = (id: string) => {
    setSelectedTeamId(id)
    const team = bootstrap?.teams.find(item => item.id === id)
    if (team?.members[0]) setOwnId(team.members[0].identity)
    void api.saveSettings({ selected_team_id: id }).catch(() => undefined)
  }

  const toggleTheme = () => {
    setDark(value => {
      const next = !value
      void api.saveSettings({ theme: next ? 'dark' : 'light' }).catch(() => undefined)
      return next
    })
  }

  return (
    <div className={`${dark ? 'dark' : ''} ${reducedMotion ? 'reduce-motion' : ''}`}>
      <AppShell page={page} onPageChange={setPage} dark={dark} onThemeToggle={toggleTheme} app={bootstrap?.app} online={Boolean(bootstrap)}>
        {startupError && <div className="app-error"><strong>本地服务未就绪</strong><span>{startupError}</span><button className="button primary" type="button" onClick={() => window.location.reload()}>重新连接</button></div>}
        {!startupError && !bootstrap && <div className="app-loading"><span className="spinner" />正在读取本地资料与队伍…</div>}
        {bootstrap && page === 'battle' && <BattlePage teams={bootstrap.teams} selectedTeamId={selectedTeamId} onTeamChange={selectTeam} ownTeam={ownTeam} rivalTeam={rivalTeam} recognition={recognition} onRecognized={report => { setRecognition(report); const first = report.opponent.find(slot => slot.pokemon)?.pokemon; if (first) setRivalId(first.id) }} ownId={ownId} rivalId={rivalId} onOwnChange={setOwnId} onRivalChange={setRivalId} settings={bootstrap.settings} onOpenDamage={() => setPage('damage')} />}
        {bootstrap && page === 'teams' && <TeamPage teams={bootstrap.teams} featured={bootstrap.featured} selectedTeamId={selectedTeamId} onSelectedTeam={setSelectedTeamId} onRefresh={refreshTeams} />}
        {bootstrap && page === 'damage' && ownTeam.length > 0 && rivalTeam.length > 0 && <DamagePage key={`${selectedTeamId}-${ownId}-${rivalId}`} teams={bootstrap.teams} selectedTeamId={selectedTeamId} onTeamChange={selectTeam} own={ownTeam.find(item => item.id === ownId) ?? ownTeam[0]} ownMember={selectedTeam?.members.find(item => item.identity === ownId)} ownTeam={ownTeam} onOwnChange={setOwnId} rival={rivalTeam.find(item => item.id === rivalId) ?? rivalTeam[0]} rivalTeam={rivalTeam} onRivalChange={setRivalId} />}
        {bootstrap && page === 'library' && <ReferencePage featured={bootstrap.featured} onOpenDamage={pokemon => { setRivalId(pokemon.id); setPage('damage') }} />}
        {bootstrap && page === 'settings' && <SettingsPage settings={bootstrap.settings} app={bootstrap.app} dark={dark} onThemeToggle={toggleTheme} reducedMotion={reducedMotion} onReducedMotion={() => setReducedMotion(value => { const next = !value; void api.saveSettings({ reduced_motion: next }).catch(() => undefined); return next })} onSettings={settings => setBootstrap(value => value ? { ...value, settings } : value)} />}
      </AppShell>
    </div>
  )
}

export default App
