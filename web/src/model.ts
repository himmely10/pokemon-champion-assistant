export type PageId = 'battle' | 'teams' | 'damage' | 'library' | 'settings'

export type PokemonFamilyBase = {
  id: string
  name: string
  dex: string
  image: string
  types: string[]
  speed: number
  form?: string | null
}

export type Pokemon = PokemonFamilyBase & {
  status?: 'confirmed' | 'review' | 'corrected'
  family_base: PokemonFamilyBase
  is_battle_form: boolean
}

export type Move = {
  id?: string
  name: string
  type: string
  category: '物理' | '特殊' | '变化'
  power: string | number | null
  accuracy: string | number | null
  usage: number | null
  damage?: [number, number]
  verdict?: string
  description: string
  status?: string
  reason?: string | null
  rolls?: number[]
  minimum?: number | null
  maximum?: number | null
  max_hp?: number | null
  current_hp?: number | null
  ko_chance?: number | null
  hit_chance?: { percent: number | null; notes: string[] }
  priority?: { original: number | null; current: number | null; notes: string[] }
  support_effects?: Array<{ key: string; label: string; side: 'attackerSide' | 'defenderSide'; state: 'applied' | 'ignored' | 'context'; reason: string }>
}

export type AbilityOption = {
  id: string
  name: string
  description: string
  trigger_label?: string | null
  scene_requirement?: { kind: 'weather' | 'terrain'; value: string } | null
  hp_requirement?: 'full' | null
}

export type BattleState = {
  hp: number
  status: string
  allies_fainted: number
  boosts: Record<'attack' | 'defense' | 'special_attack' | 'special_defense' | 'speed', number>
  ability_on: boolean
  reflect: boolean
  light_screen: boolean
  protected: boolean
  helping_hand: boolean
  friend_guard: boolean
  tailwind: boolean
  aurora_veil: boolean
  charge_boost_included: boolean
}

export type TeamMember = {
  identity: string
  points: Record<'hp' | 'attack' | 'defense' | 'special_attack' | 'special_defense' | 'speed', number | null>
  nature: string | null
  ability: string | null
  item: string | null
  moves: Array<string | null>
  pokemon: Pokemon | null
  nature_name?: string | null
  ability_name?: string | null
  item_name?: string | null
  move_names?: Array<string | null>
}

export type Team = {
  id: string
  revision: number
  name: string
  registration: 'full' | 'partial'
  members: TeamMember[]
  schema_version?: number
  dataset_id?: string
  import_source?: Record<string, unknown>
}

export type TeamImportEvidence = {
  text: string
  score: number
  suggestions?: string[]
  warning?: string
}

export type TeamImportPage = {
  mode: 'ability' | 'status'
  team_code: string | null
  code_evidence: TeamImportEvidence
  members: Array<{
    slot: number
    member: { identity: string | null }
    evidence: { name: TeamImportEvidence; warning?: string }
  }>
  source: { sha256: string; size: number[] }
}

export type TeamImportRecognition = { handle: string; page: TeamImportPage }
export type TeamImportCombineRequest = {
  ability_handle: string
  status_handle: string
  ability_review: { code: string; identities: string[] }
  status_review: { code: string; identities: string[] }
}
export type TeamImportCombineResponse = { draft: Team; warnings: string[]; notice: string }

export type AppSettings = {
  host: string
  port: number
  source: string
  selected_team_id?: string | null
  theme: 'light' | 'dark'
  reduced_motion: boolean
  obs_local?: { enabled: boolean; auth_required: boolean; port: number } | null
  password_in_memory: boolean
  password_saved: boolean
  user_directory: string
}

export type Bootstrap = {
  app: { name: string; version: string; dataset_id: string; pokemon_forms: number; api: string }
  settings: AppSettings
  teams: Team[]
  featured: Pokemon[]
}

export type PokemonDetail = Pokemon & {
  base_stats: Record<string, number>
  base_stat_total: number
  matchups: Record<'weakness' | 'resistance' | 'immune', Array<{ type: string; multiplier: number }>>
  moves: Move[]
  notice: string
  forms: Pokemon[]
  abilities: AbilityOption[]
}

export type RecognitionSlot = {
  slot: number
  status: 'recognized' | 'unknown'
  name: string | null
  similarity: number
  margin: number
  reason?: string | null
  pokemon: Pokemon | null
  candidates?: Array<{ name: string; similarity: number; pokemon: Pokemon | null }>
}

export type RecognitionReport = {
  recognized_count: number
  elapsed_seconds: number
  opponent: RecognitionSlot[]
}

export type DamageDirection = {
  attacker: Pokemon
  defender: Pokemon
  preset: string
  target_preset: string
  spread_usage?: number | null
  scenario_points?: TeamMember['points']
  scenario_nature?: string
  speed: { status: string; speed?: number; reason?: string }
  moves: Move[]
}

export type DamageResponse = {
  own: DamageDirection
  rival: DamageDirection
  own_scenarios: DamageDirection[]
  rival_scenarios: DamageDirection[]
  speed_comparison: {
    own: { status: string; speed?: number; raw_speed?: number; reason?: string }
    tiers: Array<{ name: string; speed: number; description: string; kind: 'reference' | 'common'; usage?: number; relation: '我方更快' | '同速' | '对手更快' | '待确认' }>
    reason?: string
  }
  dataset_id: string
}

export type DamageOptions = {
  pokemon: Pokemon
  forms: Array<Pokemon & { abilities: AbilityOption[] }>
  abilities: AbilityOption[]
  copiable_abilities: AbilityOption[]
  support_effects: Array<{ id: keyof Omit<BattleState, 'hp' | 'status' | 'allies_fainted' | 'boosts' | 'ability_on' | 'charge_boost_included'>; engine_id: string; label: string; group: string; description: string }>
  statuses: Array<{ id: string; name: string }>
}

export type DamageRequest = {
  environment: { weather: string; terrain: string; targets: number; critical: boolean }
  ownMember?: TeamMember
  ownFormId?: string
  rivalFormId?: string
  ownAbility?: string
  rivalAbility?: string
  copiedAbility?: string
  ownBattle?: BattleState
  rivalBattle?: BattleState
}

export type TeamOptions = {
  pokemon: Pokemon
  natures: Array<{ id: string; name: string }>
  abilities: Array<{ id: string; name: string }>
  items: Array<{ id: string; name: string }>
  moves: Array<{ id: string; name: string }>
  point_rules: { per_stat: number; total: number }
}
