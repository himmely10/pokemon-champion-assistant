import { useState } from 'react'
import { CheckCircle2, Database, Eye, HardDrive, MonitorCog, ShieldCheck, Sparkles } from 'lucide-react'
import { api } from '../api'
import type { AppSettings } from '../model'

export function SettingsPage({ settings, app, dark, onThemeToggle, reducedMotion, onReducedMotion, onSettings }: {
  settings: AppSettings
  app: { version: string; dataset_id: string; pokemon_forms: number }
  dark: boolean
  onThemeToggle: () => void
  reducedMotion: boolean
  onReducedMotion: () => void
  onSettings: (settings: AppSettings) => void
}) {
  const [section, setSection] = useState('capture')
  const items = [['capture', '采集与 OBS', MonitorCog], ['updates', '资料状态', Database], ['appearance', '外观与辅助功能', Eye], ['storage', '本地存储', HardDrive], ['about', '诊断与关于', ShieldCheck]] as const
  return <div className="standard-page settings-page">
    <section className="page-toolbar"><div><p className="eyebrow">本机设置</p><h2>设置</h2><p>采集、资料和界面偏好都保存在本机。</p></div></section>
    <section className="settings-layout">
      <nav aria-label="设置分类">{items.map(([id, label, Icon]) => <button key={id} type="button" className={section === id ? 'active' : ''} onClick={() => setSection(id)}><Icon size={19} /><span>{label}</span></button>)}</nav>
      <div className="settings-content">
        {section === 'capture' && <CaptureSettings settings={settings} onSettings={onSettings} />}
        {section === 'updates' && <DataSettings app={app} />}
        {section === 'appearance' && <AppearanceSettings dark={dark} onThemeToggle={onThemeToggle} reducedMotion={reducedMotion} onReducedMotion={onReducedMotion} />}
        {section === 'storage' && <StorageSettings settings={settings} />}
        {section === 'about' && <AboutSettings app={app} settings={settings} />}
      </div>
    </section>
  </div>
}

function SectionHeader({ kicker, title, copy }: { kicker: string; title: string; copy: string }) {
  return <header className="settings-header"><small>{kicker}</small><h2>{title}</h2><p>{copy}</p></header>
}

function CaptureSettings({ settings, onSettings }: { settings: AppSettings; onSettings: (settings: AppSettings) => void }) {
  const [host, setHost] = useState(settings.host)
  const [port, setPort] = useState(String(settings.port))
  const [password, setPassword] = useState('')
  const [source, setSource] = useState(settings.source)
  const [sources, setSources] = useState<Array<{ name: string; kind: string }>>([])
  const [status, setStatus] = useState('尚未测试 OBS 连接')
  const [busy, setBusy] = useState(false)

  const payload = () => ({ host, port: Number(port), source, ...(password ? { password } : {}) })
  const connect = async () => {
    setBusy(true)
    try {
      const result = await api.obsSources(payload())
      setSources(result.sources)
      const nextSource = source || result.sources[0]?.name || ''
      setSource(nextSource)
      onSettings(await api.saveSettings({ ...payload(), source: nextSource }))
      setPassword('')
      setStatus(`已连接 OBS ${result.version}，读取到 ${result.sources.length} 个可截图来源。`)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '连接失败')
    } finally {
      setBusy(false)
    }
  }
  const test = async () => {
    setBusy(true)
    try {
      const result = await api.obsCapture(payload())
      setStatus(`测试截图成功，识别 ${result.recognized_count}/6 个位置。`)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '截图失败')
    } finally {
      setBusy(false)
    }
  }
  const forgetPassword = async () => {
    setBusy(true)
    try {
      onSettings(await api.saveSettings({ clear_obs_password: true }))
      setPassword('')
      setStatus('已清除本机保存的 OBS 密码。')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '清除失败')
    } finally {
      setBusy(false)
    }
  }
  return <><SectionHeader kicker="OBS WEBSOCKET" title="采集与 OBS" copy="连接纯游戏画面来源，用于按需截取一帧。验证成功后，密码会由 Windows 当前用户加密保存。" /><div className={`setting-status ${status.includes('失败') ? 'error' : ''}`}><CheckCircle2 size={20} /><div><strong>{busy ? '正在处理…' : status}</strong><span>{source || '尚未选择采集来源'}</span></div></div><div className="settings-form"><label><span>主机地址</span><input value={host} onChange={event => setHost(event.target.value)} /></label><label><span>端口</span><input value={port} inputMode="numeric" onChange={event => setPort(event.target.value)} /></label><label className="full"><span>密码</span><input value={password} onChange={event => setPassword(event.target.value)} type="password" placeholder={settings.password_saved ? '已安全保存；留空则继续使用' : settings.password_in_memory ? '密码已在本次运行中加载' : '输入 OBS WebSocket 密码'} /><small>{settings.password_saved ? '密码已使用 Windows 当前用户凭据加密保存，不会返回给网页。' : '连接验证成功后安全保存；留空不会覆盖已有密码。'}</small></label><label className="full"><span>采集来源</span><select value={source} onChange={event => setSource(event.target.value)}><option value="">请选择来源</option>{(sources.length ? sources : source ? [{ name: source, kind: '已保存' }] : []).map(item => <option key={item.name} value={item.name}>{item.kind} · {item.name}</option>)}</select></label></div><div className="settings-actions"><button className="button primary" type="button" disabled={busy} onClick={() => void connect()}>连接并保存</button><button className="button quiet" type="button" disabled={busy || !source} onClick={() => void test()}>测试截图与识别</button>{settings.password_saved && <button className="button quiet" type="button" disabled={busy} onClick={() => void forgetPassword()}>清除已保存密码</button>}</div></>
}

function DataSettings({ app }: { app: { dataset_id: string; pokemon_forms: number } }) {
  return <><SectionHeader kicker="LOCAL SNAPSHOT" title="资料状态" copy="网页与桌面程序读取相同的不可变资料快照。" /><div className="version-card"><div><span>当前资料版本</span><strong>{app.dataset_id}</strong><small>{app.pokemon_forms} 个可检索形态 · 本地完整性校验通过后才会启动</small></div><span className="complete-pill"><CheckCircle2 size={15} />已加载</span></div><p className="source-notice">资料更新仍由现有的桌面更新流程完成；刷新网页即可读取下次启动时选定的新快照。</p></>
}

function AppearanceSettings({ dark, onThemeToggle, reducedMotion, onReducedMotion }: { dark: boolean; onThemeToggle: () => void; reducedMotion: boolean; onReducedMotion: () => void }) {
  return <><SectionHeader kicker="APPEARANCE" title="外观与辅助功能" copy="选项立即生效并同步写入本地设置。" /><div className="setting-row"><div><strong>深色主题</strong><span>当前为{dark ? '深色' : '浅色'}主题</span></div><button type="button" role="switch" aria-label="深色主题" aria-checked={dark} className={`switch ${dark ? 'on' : ''}`} onClick={onThemeToggle}><i /></button></div><div className="setting-row"><div><strong>减少动态效果</strong><span>关闭扫描和页面切换动画</span></div><button type="button" role="switch" aria-label="减少动态效果" aria-checked={reducedMotion} className={`switch ${reducedMotion ? 'on' : ''}`} onClick={onReducedMotion}><i /></button></div></>
}

function StorageSettings({ settings }: { settings: AppSettings }) {
  return <><SectionHeader kicker="LOCAL DATA" title="本地存储" copy="队伍和设置继续存放在桌面程序原有目录中。" /><div className="version-card"><div><span>用户数据目录</span><strong>{settings.user_directory}</strong><small>网页无法绕过浏览器安全策略直接打开该目录。</small></div></div></>
}

function AboutSettings({ app, settings }: { app: { version: string; dataset_id: string; pokemon_forms: number }; settings: AppSettings }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify({ app, obs: { host: settings.host, port: settings.port, source: settings.source }, password_stored: settings.password_saved }, null, 2))
    setCopied(true)
  }
  return <><SectionHeader kicker="DIAGNOSTICS" title="诊断与关于" copy="诊断摘要不会包含 OBS 密码或截图原图。" /><div className="about-mark"><Sparkles size={28} /><div><strong>Champion Lab</strong><span>训练家对战终端 · v{app.version}</span></div></div><div className="settings-actions"><button className="button primary" type="button" onClick={() => void copy()}>{copied ? '已复制诊断摘要' : '复制诊断摘要'}</button></div></>
}
