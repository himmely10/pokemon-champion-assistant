"""User-facing assumptions for abilities whose effect needs a battle condition.

Weather, terrain, HP and status still activate these effects automatically in the
calculator.  The checkbox is an explicit confirmation for screenshots where the
condition is known but cannot be inferred from the current UI state.
"""

ABILITY_TRIGGER_LABELS = {
    'blaze': '猛火已触发（HP≤1/3时自动生效）',
    'torrent': '激流已触发（HP≤1/3时自动生效）',
    'overgrow': '茂盛已触发（HP≤1/3时自动生效）',
    'swarm': '虫之预感已触发（HP≤1/3时自动生效）',
    'unburden': '轻装已触发（道具已失去）',
    'chlorophyll': '叶绿素已触发（大晴天时自动生效）',
    'swift-swim': '悠游自如已触发（下雨时自动生效）',
    'sand-rush': '拨沙已触发（沙暴时自动生效）',
    'slush-rush': '拨雪已触发（下雪时自动生效）',
    'surge-surfer': '冲浪之尾已触发（电气场地时自动生效）',
    'quick-feet': '飞毛腿已触发（陷入异常状态时自动生效）',
    'protosynthesis': '古代活性已触发（大晴天／驱劲能量；速度为最高能力时速度×1.5）',
    'quark-drive': '夸克充能已触发（电气场地／驱劲能量；速度为最高能力时速度×1.5）',
    'solar-power': '太阳之力已触发（大晴天时自动生效）',
    'sand-force': '沙之力已触发（沙暴时自动生效）',
    'guts': '毅力已触发（陷入异常状态时自动生效）',
    'marvel-scale': '神奇鳞片已触发（陷入异常状态时自动生效）',
    'grass-pelt': '草之毛皮已触发（青草场地时自动生效）',
    'multiscale': '多重鳞片已触发（满 HP 时自动生效）',
    'gale-wings': '疾风之翼已触发（满 HP 且使用飞行招式时自动生效）',
    'merciless': '不仁不义已触发（攻击中毒／剧毒目标时自动生效）',
    'rivalry': '斗争心按有利情景触发（对手同性时增伤）',
    'sand-veil': '沙隐已触发（沙暴时自动生效；对手命中率×0.8）',
    'snow-cloak': '雪隐已触发（下雪时自动生效；对手命中率×0.8）',
    'tangled-feet': '蹒跚已触发（混乱时生效；对手命中率×0.5）',
    'slow-start': '慢启动仍在生效',
    'electromorphosis': '电力转换已进入充电状态',
    'analytic': '分析：本次按后手攻击',
    'plus': '正电：对应特性同伴在场',
    'minus': '负电：对应特性同伴在场',
    'flash-fire': '引火已吸收火属性招式',
    'stakeout': '蹲守：目标本回合刚换入',
    'intimidate': '本次入场威吓生效',
    'intrepid-sword': '本次入场触发不挠之剑',
    'dauntless-shield': '本次入场触发不屈之盾',
    'teraform-zero': '太晶变形归零已触发',
}

# Conditions with one unambiguous global selector are kept bidirectionally in
# sync with the checkbox in the damage UI.  Abilities with alternative triggers
# (for example Booster Energy) deliberately remain independent.
ABILITY_SCENE_REQUIREMENTS = {
    'chlorophyll': ('weather', 'Sun'),
    'solar-power': ('weather', 'Sun'),
    'swift-swim': ('weather', 'Rain'),
    'sand-rush': ('weather', 'Sand'),
    'sand-force': ('weather', 'Sand'),
    'sand-veil': ('weather', 'Sand'),
    'slush-rush': ('weather', 'Snow'),
    'snow-cloak': ('weather', 'Snow'),
    'surge-surfer': ('terrain', 'Electric'),
    'grass-pelt': ('terrain', 'Grassy'),
}

ABILITY_HP_REQUIREMENTS = {
    'gale-wings': 'full',
    'multiscale': 'full',
}


def effective_accuracy(move, attacker, defender, attacker_battle, defender_battle, environment):
    """Return the displayed hit chance and every applied accuracy modifier.

    Damage rolls remain conditional on a hit.  This companion value deliberately
    handles only deterministic inputs represented by the current battle UI.
    """
    if not move or move.get('accuracy') is None:
        return {'percent': None, 'notes': []}
    base = move['accuracy']
    attacker_ability = attacker.get('ability')
    defender_ability = defender.get('ability')
    if 'no-guard' in {attacker_ability, defender_ability}:
        return {'percent': 100, 'notes': ['无防守：必定命中']}

    weather = environment.get('weather', '')
    move_key = move.get('key')
    if move_key in {'thunder', 'hurricane'}:
        if weather == 'Rain':
            return {'percent': 100, 'notes': ['下雨：必定命中']}
        if weather == 'Sun':
            base = 50
    elif move_key == 'blizzard' and weather == 'Snow':
        return {'percent': 100, 'notes': ['下雪：必定命中']}

    modifier = 1.0
    notes = []
    if attacker_ability == 'compound-eyes':
        modifier *= 1.3; notes.append('复眼 ×1.3')
    if attacker_ability == 'hustle' and move.get('category') == 'physical':
        modifier *= .8; notes.append('活力（物理）×0.8')
    if attacker_ability == 'victory-star':
        modifier *= 1.1; notes.append('胜利之星 ×1.1')
    if defender_ability == 'sand-veil' and (weather == 'Sand' or defender_battle.get('ability_on')):
        modifier *= .8; notes.append('沙隐 ×0.8')
    if defender_ability == 'snow-cloak' and (weather == 'Snow' or defender_battle.get('ability_on')):
        modifier *= .8; notes.append('雪隐 ×0.8')
    if defender_ability == 'tangled-feet' and defender_battle.get('ability_on'):
        modifier *= .5; notes.append('蹒跚 ×0.5')
    return {'percent': min(100, round(base * modifier, 1)), 'notes': notes}


def effective_priority(move, attacker, attacker_battle, environment, *, grounded=True, full_hp=None):
    """Return original/current priority for conditions represented by the UI."""
    if not move:
        return {'original': None, 'current': None, 'notes': []}
    original = move.get('priority')
    if original is None:
        return {'original': None, 'current': None, 'notes': []}
    current = original
    notes = []
    if move.get('key') == 'grassy-glide' and environment.get('terrain') == 'Grassy' and grounded:
        current = max(current, 1); notes.append('青草场地（使用者接地）')
    if full_hp is None:
        full_hp = attacker_battle.get('hp', 0) == 0
    if attacker.get('ability') == 'gale-wings' and move.get('type') == 'flying' and (
        full_hp or attacker_battle.get('ability_on')):
        current += 1; notes.append('疾风之翼（满 HP）')
    if attacker.get('ability') == 'prankster' and move.get('category') == 'status':
        current += 1; notes.append('恶作剧之心（变化招式）')
    return {'original': original, 'current': current, 'notes': notes}
