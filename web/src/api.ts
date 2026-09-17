import type { AppSettings, Bootstrap, DamageOptions, DamageRequest, DamageResponse, Pokemon, PokemonDetail, RecognitionReport, Team, TeamOptions, TeamImportRecognition, TeamImportCombineRequest, TeamImportCombineResponse } from './model'

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

async function responseJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({})) as { error?: string }
  if (!response.ok) throw new ApiError(body.error ?? `本地接口请求失败（${response.status}）`, response.status)
  return body as T
}

export async function getJson<T>(path: string): Promise<T> {
  return responseJson<T>(await fetch(path, { headers: { Accept: 'application/json' } }))
}

export async function postJson<T>(path: string, payload: unknown): Promise<T> {
  return responseJson<T>(await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export const api = {
  bootstrap: () => getJson<Bootstrap>('/api/bootstrap'),
  teams: () => getJson<Team[]>('/api/teams'),
  saveTeam: (team: Team) => postJson<Team>('/api/teams', team),
  deleteTeam: (team: Pick<Team, 'id' | 'revision'>) => postJson<{ deleted: boolean }>('/api/teams/delete', team),
  searchPokemon: (query: string, limit = 30, offset = 0) => getJson<Pokemon[]>(`/api/pokemon?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`),
  pokemonDetail: (id: string) => getJson<PokemonDetail>(`/api/pokemon/detail?id=${encodeURIComponent(id)}`),
  teamOptions: (id: string) => getJson<TeamOptions>(`/api/pokemon/options?id=${encodeURIComponent(id)}`),
  damageOptions: (id: string) => getJson<DamageOptions>(`/api/damage/options?id=${encodeURIComponent(id)}`),
  saveSettings: (settings: Partial<AppSettings> & { password?: string; clear_obs_password?: boolean }) => postJson<AppSettings>('/api/settings', settings),
  obsSources: (settings: Partial<AppSettings> & { password?: string }) => postJson<{ sources: Array<{ name: string; kind: string }>; version: string }>('/api/obs/sources', settings),
  obsCapture: (settings: Partial<AppSettings> & { password?: string }) => postJson<RecognitionReport>('/api/obs/capture', settings),
  damage: (ownId: string, rivalId: string, request: DamageRequest) => postJson<DamageResponse>('/api/damage/quick', {
    own_id: ownId,
    rival_id: rivalId,
    environment: request.environment,
    own_member: request.ownMember,
    own_form_id: request.ownFormId,
    rival_form_id: request.rivalFormId,
    own_ability: request.ownAbility,
    rival_ability: request.rivalAbility,
    copied_ability: request.copiedAbility,
    own_battle: request.ownBattle,
    rival_battle: request.rivalBattle,
  }),
  recognize: async (file: File) => responseJson<RecognitionReport>(await fetch('/api/recognize', {
    method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream', Accept: 'application/json' }, body: file,
  })),
  teamImportRecognize: async (image: Blob, mode: 'ability' | 'status') => responseJson<TeamImportRecognition>(await fetch(`/api/team-import/recognize?mode=${mode}`, {
    method: 'POST', headers: { 'Content-Type': image.type || 'application/octet-stream', Accept: 'application/json' }, body: image,
  })),
  teamImportObsCapture: (settings: Partial<AppSettings> & { password?: string }) => postJson<{ data_url: string }>('/api/team-import/obs-capture', settings),
  teamImportCombine: (payload: TeamImportCombineRequest) => postJson<TeamImportCombineResponse>('/api/team-import/combine', payload),
}
