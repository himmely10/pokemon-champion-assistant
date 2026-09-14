// Local, bounded stdin/stdout bridge. No network, eval, or execution of user strings.
'use strict';
const calc = require('./vendor/smogon-calc/dist/adaptable');
const {Generations} = require('./vendor/smogon-calc/dist/data');
const {getFinalSpeed, checkItem, checkAirLock} = require('./vendor/smogon-calc/dist/mechanics/util');
const gen = Generations.get(0);
const blocked = new Set(['ragefist','beatup','present','magnitude','pursuit','assurance','payback',
  'lashout','round','echoedvoice','stompingtantrum','spitup','naturalgift','rollout','iceball','trumpcard',
  'counter','mirrorcoat','metalburst','comeuppance','bide','endeavor','superfang','naturesmadness',
  'ruination','fissure','guillotine','horndrill','sheercold','ficklebeam','meteorbeam']);
const id = s => s.toLowerCase().replace(/[^a-z0-9]/g, '');
function pokemon(input) {
  if (!gen.species.get(id(input.name))) throw Error('规则快照中没有该形态');
  if (input.options.item && !gen.items.get(id(input.options.item))) throw Error('规则快照不支持该道具');
  if (input.options.ability !== '(No Ability)' && !gen.abilities.get(id(input.options.ability))) throw Error('规则快照不支持该特性');
  if (!gen.natures.get(id(input.options.nature))) throw Error('规则快照不支持该性格');
  const p = new calc.Pokemon(gen, input.name, input.options);
  for (const [key, value] of Object.entries(input.baseStats)) {
    if (p.species.baseStats[key] !== value) throw Error('本地种族值与规则快照不同，需更新规则后再计算');
  }
  if (JSON.stringify([...p.types].sort()) !== JSON.stringify([...input.types].sort())) throw Error('本地属性与规则快照不同');
  return p;
}
function supportEffects(job, result) {
  const desc = result.rawDesc;
  const screens = ['isReflect', 'isLightScreen', 'isAuroraVeil'];
  const keys = ['isHelpingHand', ...screens, 'isProtected', 'isFriendGuard', 'isTailwind'];
  const effects = [];
  for (const side of ['attackerSide', 'defenderSide']) {
    const input = job.field[side] || {};
    for (const key of keys) {
      if (!input[key]) continue;
      let state = 'ignored', reason;
      if (key === 'isTailwind') {
        state = 'context'; reason = '速度条件已传入引擎；不是通用伤害倍率。';
      } else if ((key === 'isHelpingHand') !== (side === 'attackerSide')) {
        reason = key === 'isHelpingHand' ? '本方是防守方，帮助只作用于攻击方。' : '本方是攻击方，保护效果只作用于防守方。';
      } else if (desc[key]) {
        state = 'applied'; reason = '引擎已按本招机制计入；不代表一定造成非零伤害。';
      } else if (screens.includes(key) && desc.isCritical) {
        reason = '本次为要害，忽略墙与幕。';
      } else if (['isReflect','isLightScreen'].includes(key) && desc.isAuroraVeil) {
        reason = '本次按极光幕处理，与两墙不叠加。';
      } else if (key === 'isReflect' && result.move.category !== 'Physical') {
        reason = '本招不是物理招式。';
      } else if (key === 'isLightScreen' && result.move.category !== 'Special') {
        reason = '本招不是特殊招式。';
      } else if (desc.isProtected) {
        reason = '本次被守住，未进入该伤害修正。';
      } else if (screens.includes(key) && result.attacker.hasAbility('Infiltrator')) {
        reason = '攻击方穿透特性忽略墙与幕。';
      } else if (screens.includes(key) && result.move.named('Brick Break','Psychic Fangs','Raging Bull')) {
        reason = '本招在伤害前拆除墙与幕。';
      } else if (key === 'isProtected' && (result.move.breaksProtect ||
          (result.attacker.hasAbility('Unseen Fist','Piercing Drill') && result.move.flags.contact))) {
        reason = '本招或攻击方特性可穿透守住。';
      } else if (typeof result.damage === 'number' && result.damage > 0) {
        reason = '本招使用固定或特殊直接伤害，不采用此伤害修正。';
      } else {
        reason = '引擎未计入此效果：可能为固定伤害、免疫、穿透或拆墙等招式机制。';
      }
      effects.push({side,key,state,reason});
    }
  }
  return effects;
}
function run(job) {
  try {
    if (job.statusMove) return {status:'status_move', reason:job.statusReason || '变化招式：没有本次直接伤害范围'};
    if (job.error) return {status:'unavailable', reason:job.error};
    if (job.kind === 'speed') {
      const p = pokemon(job.attacker), field = new calc.Field(job.field);
      checkItem(p, field.isMagicRoom); checkAirLock(p, field);
      return {status:'ok', raw_speed:p.rawStats.spe, speed:getFinalSpeed(gen,p,field,field.attackerSide)};
    }
    const data = gen.moves.get(id(job.move));
    if (!data) throw Error('该招式尚未进入 Champions 规则快照');
    if (data.category === 'Status') return {status:'status_move', reason:'变化招式：没有本次直接伤害范围'};
    if (data.multihit && !(Array.isArray(data.multihit) && data.multihit[0] === 2 && data.multihit[1] === 5))
      throw Error('特殊多段招式的逐段威力尚未核验，本版暂不计算');
    if (data.id === 'electroshot' && typeof job.charge_boost_included !== 'boolean')
      throw Error('电光束：请明确特攻等级是否已包含本次充能提升');
    if (blocked.has(data.id)) throw Error('该特殊招式尚未核验或需要额外战斗输入，本版暂不计算');
    const a = pokemon(job.attacker), d = pokemon(job.defender);
    if (data.id === 'electroshot' && a.hasAbility('Simple') && !job.charge_boost_included)
      throw Error('电光束＋单纯：请将实际充能后的特攻等级明确填入，并选择已包含充能');
    const aRaw = {...a.rawStats}, dRaw = {...d.rawStats};
    if (data.id === 'electroshot' && job.charge_boost_included)
      a.boosts.spa -= a.hasAbility('Contrary') ? -1 : 1;
    const move = new calc.Move(gen, data.name, {isCrit:job.critical, hits:job.hits || 1, overrides:
      data.id === 'lastrespects' ? {basePower:50 * (1 + job.attacker.options.alliesFainted)} : undefined});
    const result = calc.calculate(gen, a, d, move, new calc.Field(job.field));
    const [minimum, maximum] = result.range();
    if (![minimum, maximum].every(Number.isFinite)) throw Error('引擎没有返回有效范围');
    const output = {status:'ok', minimum, maximum, rolls:result.damage,
      percent_min:minimum*100/dRaw.hp, percent_max:maximum*100/dRaw.hp,
      max_hp:dRaw.hp, current_hp:job.defender.options.curHP || dRaw.hp,
      attacker_stats:aRaw, defender_stats:dRaw, details:result.rawDesc,
      support_effects:supportEffects(job, result),
      note:'命中后本次直接伤害；百分比以最大 HP 为分母，不含后续回合与命中率'};
    if (data.id === 'electroshot') output.charge_boost_included = job.charge_boost_included;
    if (data.multihit && !job.hits) {
      const scenarios = [2,3,4,5].map(hits => ({hits,...run({...job,hits})}));
      output.multi_hit = {single:{...output},scenarios};
      output.note += '；主范围为单段，2–5 段按逐段特性与道具分别计算';
    }
    return output;
  } catch (error) { return {status:'unavailable', reason:String(error.message)}; }
}
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {input += chunk;if (input.length > 4000000) process.exit(2);});
process.stdin.on('end', () => {
  try {
    const jobs = JSON.parse(input);
    if (!Array.isArray(jobs) || jobs.length > 300) throw Error('Invalid job count');
    process.stdout.write(JSON.stringify(jobs.map(run)));
  } catch (error) {process.stderr.write(String(error.message));process.exitCode=1;}
});
