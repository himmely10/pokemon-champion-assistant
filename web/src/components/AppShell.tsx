import type { ReactNode } from 'react'
import { BookOpen, ChevronLeft, Database, FlaskConical, Moon, Settings, ShieldCheck, Swords, Sun, Users } from 'lucide-react'
import type { PageId } from '../model'

const navItems: Array<{ id: PageId; label: string; icon: typeof Swords }> = [
  { id: 'battle', label: '对战台', icon: Swords },
  { id: 'teams', label: '队伍仓库', icon: Users },
  { id: 'damage', label: '伤害计算', icon: FlaskConical },
  { id: 'library', label: '资料库', icon: Database },
  { id: 'settings', label: '设置', icon: Settings },
]

export function AppShell({ page, onPageChange, dark, onThemeToggle, app, online, children }: {
  page: PageId
  onPageChange: (page: PageId) => void
  dark: boolean
  onThemeToggle: () => void
  app?: { version: string; dataset_id: string }
  online: boolean
  children: ReactNode
}) {
  const active = navItems.find(item => item.id === page) ?? navItems[0]
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true"><span /><i /></div>
          <div><strong>CHAMPION</strong><span>LAB</span></div>
        </div>

        <nav>
          {navItems.map(item => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                type="button"
                className={page === item.id ? 'active' : ''}
                onClick={() => onPageChange(item.id)}
                aria-current={page === item.id ? 'page' : undefined}
                aria-label={item.label}
                title={item.label}
              >
                <Icon size={21} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="sidebar-foot">
          <div className="offline-state"><ShieldCheck size={17} /><span>{online ? '本地接口已就绪' : '正在连接本地接口'}</span></div>
          <small>v{app?.version ?? '…'} · {app?.dataset_id?.slice(0, 12) ?? '读取资料中'}</small>
        </div>
      </aside>

      <main className="app-main">
        <header className="topbar">
          <div className="page-heading">
            <button className="mobile-back" type="button" aria-label="展开导航"><ChevronLeft size={20} /></button>
            <div><small>训练家对战终端</small><h1>{active.label}</h1></div>
          </div>
          <div className="topbar-actions">
            <button className="status-pill" type="button"><span className={`status-dot ${online ? '' : 'pending'}`} />{online ? '本地服务已连接' : '连接中'}</button>
            <button className="icon-button" type="button" onClick={onThemeToggle} aria-label={dark ? '切换到浅色主题' : '切换到暗色主题'} title={dark ? '浅色主题' : '暗色主题'}>
              {dark ? <Sun size={19} /> : <Moon size={19} />}
            </button>
            <button className="icon-button help-button" type="button" onClick={() => onPageChange('settings')} aria-label="打开使用帮助" title="设置与使用说明"><BookOpen size={19} /></button>
          </div>
        </header>
        <div className="page-content" id="main-content">{children}</div>
      </main>
    </div>
  )
}
