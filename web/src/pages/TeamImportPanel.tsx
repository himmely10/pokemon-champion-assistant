import { useEffect, useRef, useState } from 'react'
import { Camera, Check, ImagePlus, RefreshCw, Search, X } from 'lucide-react'
import { api, ApiError } from '../api'
import type { AppSettings, Pokemon, Team, TeamImportRecognition } from '../model'

type Mode = 'ability' | 'status'
type PageState = {
  blob: Blob | null
  preview: string
  result: TeamImportRecognition | null
  code: string
  identities: string[]
  identityLabels: string[]
  confirmed: boolean
  loading: boolean
  error: string
}

const emptyPage = (): PageState => ({ blob: null, preview: '', result: null, code: '', identities: [], identityLabels: [], confirmed: false, loading: false, error: '' })
const pageNames: Record<Mode, string> = { ability: '能力页', status: '状态页' }

function IdentityPicker({ value, label, onChange }: { value: string; label: string; onChange: (identity: string, name: string) => void }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Pokemon[]>([])
  useEffect(() => {
    if (!open || !query.trim()) return
    let active = true
    const timer = window.setTimeout(() => {
      api.searchPokemon(query.trim(), 30).then(items => { if (active) setResults(items) }).catch(() => { if (active) setResults([]) })
    }, 180)
    return () => { active = false; window.clearTimeout(timer) }
  }, [open, query])
  return <div className="import-identity">
    <button className="button quiet" type="button" onClick={() => setOpen(!open)} aria-expanded={open}>{label || value || '未识别'} · 修改</button>
    {open && <div className="import-identity-search"><label><Search size={15} /><input aria-label="搜索宝可梦或形态" value={query} onChange={event => setQuery(event.target.value)} placeholder="输入宝可梦或形态" /></label><div className="import-identity-results">{results.map(item => <button type="button" key={item.id} onClick={() => { onChange(item.id, item.name); setOpen(false); setQuery('') }}>{item.name}</button>)}</div></div>}
  </div>
}

export function TeamImportPanel({ settings, onDraft, onCancel }: {
  settings: AppSettings
  onDraft: (draft: Team, notice: string) => void
  onCancel: () => void
}) {
  const [pages, setPages] = useState<Record<Mode, PageState>>({ ability: emptyPage(), status: emptyPage() })
  const [source, setSource] = useState(settings.source ?? '')
  const [password, setPassword] = useState('')
  const [sources, setSources] = useState<string[]>([])
  const [obsBusy, setObsBusy] = useState(false)
  const [combining, setCombining] = useState(false)
  const [message, setMessage] = useState('')
  const [enlarged, setEnlarged] = useState<Mode | null>(null)
  const generations = useRef<Record<Mode, number>>({ ability: 0, status: 0 })
  const combineVersion = useRef(0)
  const mounted = useRef(true)
  const urls = useRef(new Set<string>())
  const closeLightbox = useRef<HTMLButtonElement>(null)
  const lightbox = useRef<HTMLDialogElement>(null)
  const previewButtons = useRef<Record<Mode, HTMLButtonElement | null>>({ ability: null, status: null })

  useEffect(() => {
    mounted.current = true
    const currentUrls = urls.current
    // Lifecycle refs intentionally invalidate in-flight requests on unmount.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
    return () => { mounted.current = false; combineVersion.current++; for (const url of currentUrls) URL.revokeObjectURL(url) }
  }, [])
  useEffect(() => {
    if (!enlarged) return
    const dialog = lightbox.current
    const previews = previewButtons.current
    if (dialog && typeof dialog.showModal === 'function') dialog.showModal()
    else dialog?.setAttribute('open', '')
    closeLightbox.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); setEnlarged(null) } }
    window.addEventListener('keydown', onKeyDown)
    return () => { window.removeEventListener('keydown', onKeyDown); if (dialog?.open && typeof dialog.close === 'function') dialog.close(); previews[enlarged]?.focus() }
  }, [enlarged])

  const patchPage = (mode: Mode, change: Partial<PageState>) => { combineVersion.current++; setPages(current => ({ ...current, [mode]: { ...current[mode], ...change } })) }

  const recognize = async (mode: Mode, blob: Blob, preview: string, retry = false) => {
    const generation = ++generations.current[mode]
    combineVersion.current++
    setMessage('')
    setPages(current => ({ ...current, [mode]: {
      ...current[mode], blob, preview, result: null, confirmed: false, loading: true, error: '',
      code: retry ? current[mode].code : '', identities: retry ? current[mode].identities : [],
      identityLabels: retry ? current[mode].identityLabels : [],
    } }))
    try {
      const result = await api.teamImportRecognize(blob, mode)
      if (generations.current[mode] !== generation) return false
      setPages(current => ({ ...current, [mode]: {
        ...current[mode], result, loading: false, error: '', confirmed: false,
        code: retry && current[mode].code ? current[mode].code : result.page.team_code ?? '',
        identities: retry && current[mode].identities.length === 6 ? current[mode].identities : result.page.members.map(item => item.member.identity ?? ''),
        identityLabels: retry && current[mode].identityLabels.length === 6 ? current[mode].identityLabels : result.page.members.map(item => item.evidence.name.text ?? ''),
      } }))
      return true
    } catch (error) {
      if (generations.current[mode] !== generation) return false
      patchPage(mode, { loading: false, error: error instanceof Error ? error.message : '识别失败' })
      return false
    }
  }

  const chooseFile = (mode: Mode, file?: File) => {
    if (!file) return
    const old = pages[mode].preview
    if (old && urls.current.has(old)) { URL.revokeObjectURL(old); urls.current.delete(old) }
    const preview = URL.createObjectURL(file)
    urls.current.add(preview)
    void recognize(mode, file, preview)
  }

  const connection = async () => {
    if (!source.trim()) throw new Error('请先填写或选择 OBS 来源。')
    if (password) {
      await api.saveSettings({ source: source.trim(), password })
      setPassword('')
    }
    return { host: settings.host, port: settings.port, source: source.trim() }
  }

  const loadSources = async () => {
    setObsBusy(true)
    setMessage('')
    try {
      if (password) {
        await api.saveSettings({ password })
        setPassword('')
      }
      const response = await api.obsSources({ host: settings.host, port: settings.port })
      setSources(response.sources.map(item => item.name))
    } catch (error) { setMessage(error instanceof Error ? error.message : 'OBS 来源读取失败') }
    finally { setObsBusy(false) }
  }

  const capture = async (mode: Mode) => {
    const captureGeneration = ++generations.current[mode]
    patchPage(mode, { confirmed: false, loading: true, error: '' })
    setObsBusy(true)
    setMessage('')
    try {
      const opts = await connection()
      const response = await api.teamImportObsCapture(opts)
      if (generations.current[mode] !== captureGeneration) return
      const blob = await fetch(response.data_url).then(value => value.blob())
      if (generations.current[mode] !== captureGeneration) return
      const old = pages[mode].preview
      if (old && urls.current.has(old)) { URL.revokeObjectURL(old); urls.current.delete(old) }
      const preview = URL.createObjectURL(blob)
      urls.current.add(preview)
      await recognize(mode, blob, preview)
    } catch (error) {
      if (generations.current[mode] === captureGeneration) patchPage(mode, { loading: false, error: error instanceof Error ? error.message : 'OBS 截图失败' })
    }
    finally { setObsBusy(false) }
  }

  const setIdentity = (mode: Mode, index: number, identity: string, name: string) => {
    const identities = [...pages[mode].identities]
    const identityLabels = [...pages[mode].identityLabels]
    identities[index] = identity
    identityLabels[index] = name
    patchPage(mode, { identities, identityLabels, confirmed: false })
  }

  const combine = async () => {
    const ability = pages.ability
    const status = pages.status
    if (!ability.result || !status.result || !ability.confirmed || !status.confirmed) return
    const version = combineVersion.current
    setCombining(true)
    setMessage('')
    try {
      const result = await api.teamImportCombine({
        ability_handle: ability.result.handle,
        status_handle: status.result.handle,
        ability_review: { code: ability.code.trim().toUpperCase(), identities: ability.identities },
        status_review: { code: status.code.trim().toUpperCase(), identities: status.identities },
      })
      if (!mounted.current || combineVersion.current !== version) return
      onDraft(result.draft, [result.notice, ...result.warnings].filter(Boolean).join(' '))
    } catch (error) {
      if (!mounted.current || combineVersion.current !== version) return
      if (error instanceof ApiError && error.status === 409 && error.message.includes('过期') && ability.blob && status.blob) {
        setMessage('复核已过期，正在从原图重新识别两页。请保留校正并再次核对。')
        const refreshed = await Promise.all([
          recognize('ability', ability.blob, ability.preview, true),
          recognize('status', status.blob, status.preview, true),
        ])
        if (mounted.current) setMessage(refreshed.every(Boolean)
          ? '原图已重新识别；已保留校正，请重新核对两页后再合并。'
          : '部分原图重新识别失败；请查看对应页面错误并重试，之后重新核对两页。')
      } else setMessage(error instanceof Error ? error.message : '合并失败；请核对两页。')
    }
    finally { if (mounted.current) setCombining(false) }
  }

  const canCombine = (['ability', 'status'] as const).every(mode => pages[mode].result && pages[mode].confirmed && !pages[mode].loading)

  return <section className="team-import-panel" aria-label="截图导入队伍">
    <div className="team-import-head"><div><p className="eyebrow">本机 OCR · 不会自动保存</p><h3>导入队伍截图</h3><p>分别提供能力页与状态页，核对队伍码和每个槽位后，再载入未保存的队伍草稿。</p></div><button className="icon-button" type="button" aria-label="关闭截图导入" onClick={onCancel}><X size={18} /></button></div>
    <div className="team-import-obs"><label>OBS 来源 <input aria-label="OBS 来源" value={source} onChange={event => setSource(event.target.value)} list="team-import-sources" placeholder="在设置中选择或输入来源" /></label><datalist id="team-import-sources">{sources.map(item => <option value={item} key={item}>{item}</option>)}</datalist>{!settings.password_saved && <label>OBS 密码 <input aria-label="OBS 密码" type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="off" placeholder="仅当前 Windows 用户保存" /></label>}<button className="button quiet" type="button" disabled={obsBusy} onClick={() => void loadSources()}>读取 OBS 来源</button></div>
    <div className="team-import-pages">{(['ability', 'status'] as const).map(mode => {
      const page = pages[mode]
      return <section className="team-import-page" key={mode} aria-label={pageNames[mode]}><div className="team-import-page-head"><h4>{pageNames[mode]}</h4><span>{page.result ? '识别完成 · 待核对' : page.loading ? '正在识别…' : '等待截图'}</span></div><div className="team-import-actions"><label className="button secondary"><ImagePlus size={16} />选择图片<input type="file" accept="image/png,image/jpeg,image/webp,image/bmp" onChange={event => { chooseFile(mode, event.target.files?.[0]); event.target.value = '' }} /></label><button className="button secondary" type="button" disabled={obsBusy || page.loading} onClick={() => void capture(mode)}><Camera size={16} />从 OBS 截图</button>{page.blob && <button className="button quiet" type="button" disabled={page.loading} onClick={() => void recognize(mode, page.blob!, page.preview, true)}><RefreshCw size={15} />重新识别原图</button>}</div>
        {page.preview && <button ref={element => { previewButtons.current[mode] = element }} className="team-import-preview" type="button" onClick={() => setEnlarged(mode)} aria-label={`放大查看${pageNames[mode]}原图`}><img src={page.preview} alt={`${pageNames[mode]}原图预览`} /><span>点击放大核对原图</span></button>}
        {page.loading && <output>正在识别{pageNames[mode]}，请稍候…</output>}{page.error && <p className="import-error" role="alert">{page.error}</p>}
        {page.result && <div className="team-import-review"><label>队伍码 <input value={page.code} maxLength={10} onChange={event => patchPage(mode, { code: event.target.value.toUpperCase(), confirmed: false })} aria-label={`${pageNames[mode]}队伍码`} /></label><small>原始识别：{page.result.page.code_evidence.text || '未识别'}</small><div className="team-import-slots">{page.result.page.members.map((item, index) => <div key={item.slot}><span>槽位 {item.slot}</span><span>{item.evidence.name.text || '未识别'} · {Math.round(item.evidence.name.score * 100)}%</span><IdentityPicker value={page.identities[index] || ''} label={page.identityLabels[index] || ''} onChange={(value, name) => setIdentity(mode, index, value, name)} /></div>)}</div><button className={`button ${page.confirmed ? 'secondary' : 'primary'}`} type="button" disabled={page.code.trim().length !== 10 || page.identities.length !== 6 || page.identities.some(value => !value)} onClick={() => patchPage(mode, { confirmed: !page.confirmed })}><Check size={16} />{page.confirmed ? '已核对（点击撤销）' : `确认${pageNames[mode]}已核对`}</button></div>}
      </section>
    })}</div>
    {message && <p className="import-error" role="alert">{message}</p>}
    <div className="team-import-footer"><p>合并后仍需在编辑器核对未知字段；只有点击“保存队伍”才会写入仓库。</p><button className="button primary" type="button" disabled={!canCombine || combining} onClick={() => void combine()}>{combining ? '正在合并…' : '载入未保存草稿'}</button></div>
    {enlarged && <dialog ref={lightbox} className="team-import-lightbox" aria-label={`放大查看${pageNames[enlarged]}原图`} onCancel={event => { event.preventDefault(); setEnlarged(null) }}><button ref={closeLightbox} className="button quiet" type="button" onClick={() => setEnlarged(null)}>关闭放大图</button><img src={pages[enlarged].preview} alt={`${pageNames[enlarged]}原图`} /></dialog>}
  </section>
}
