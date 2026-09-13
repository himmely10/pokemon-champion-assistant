"""Stable battle keys and user-facing descriptions; damage remains engine-owned."""

SUPPORT_EFFECTS = (
    ('helping_hand', 'isHelpingHand', '本次受到帮助', '进攻辅助',
     '仅当此方是本招攻击方时适用。携带帮助不代表已经受到帮助；固定伤害等由规则判断。'),
    ('reflect', 'isReflect', '反射壁', '防守保护',
     '此方受物理招式攻击时适用；要害、穿透与拆墙等按规则判断。'),
    ('light_screen', 'isLightScreen', '光墙', '防守保护',
     '此方受特殊招式攻击时适用；要害、穿透与拆墙等按规则判断。'),
    ('aurora_veil', 'isAuroraVeil', '极光幕', '防守保护',
     '表示此方已有极光幕，不推演施放条件；与反射壁、光墙不重复叠加。'),
    ('protected', 'isProtected', '本次守住', '防守保护',
     '保护此方宝可梦；可穿透招式按规则判断，不计算连续守住成功率。'),
    ('friend_guard', 'isFriendGuard', '同伴提供友情防守', '防守保护',
     '来自仍在场的同伴；不是此宝可梦自身特性，也不自动由配招或特性勾选。'),
    ('tailwind', 'isTailwind', '此方顺风', '速度条件',
     '影响速度条件，不是通用伤害倍率；速度相关招式依规则处理。'),
)


def engine_side(battle):
    return {engine: bool(battle.get(key, False)) for key, engine, *_ in SUPPORT_EFFECTS}


def effect_summary(result):
    labels = {engine: label for _, engine, label, *_ in SUPPORT_EFFECTS}
    states = {'applied': '本招适用', 'ignored': '本招忽略', 'context': '条件输入'}
    return '\n'.join(
        f"{'攻击方' if effect['side']=='attackerSide' else '防守方'} · {labels[effect['key']]} · "
        f"已启用 / {states[effect['state']]}：{effect['reason']}"
        for effect in result.get('support_effects', [])) or '无额外辅助效果；携带招式不代表本次已生效。'
