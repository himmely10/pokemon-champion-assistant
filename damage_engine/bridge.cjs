// Local, bounded stdin/stdout bridge. No network, eval, or execution of user strings.
'use strict';
const calc = require('./vendor/smogon-calc/dist/adaptable');
const {Generations} = require('./vendor/smogon-calc/dist/data');
const gen = Generations.get(0);
const blocked = new Set(['ragefist','beatup','present','magnitude','pursuit','assurance','payback',
  'lashout','round','echoedvoice','stompingtantrum','spitup','naturalgift','rollout','iceball','trumpcard',
  'counter','mirrorcoat','metalburst','comeuppance','bide','endeavor','superfang','naturesmadness',
  'ruination','fissure','guillotine','horndrill','sheercold','ficklebeam','meteorbeam','electroshot']);
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
function run(job) {
  try {
    if (job.statusMove) return {status:'status_move', reason:'变化招式：没有本次直接伤害范围'};
    if (job.error) return {status:'unavailable', reason:job.error};
    const data = gen.moves.get(id(job.move));
    if (!data) throw Error('该招式尚未进入 Champions 规则快照');
    if (data.category === 'Status') return {status:'status_move', reason:'变化招式：没有本次直接伤害范围'};
    if (data.multihit) throw Error('多段招式：本版尚未设置命中段数情景');
    if (blocked.has(data.id)) throw Error('该特殊招式尚未核验或需要额外战斗输入，本版暂不计算');
    const a = pokemon(job.attacker), d = pokemon(job.defender);
    const aRaw = {...a.rawStats}, dRaw = {...d.rawStats};
    const move = new calc.Move(gen, data.name, {isCrit:job.critical, overrides:
      data.id === 'lastrespects' ? {basePower:50 * (1 + job.attacker.options.alliesFainted)} : undefined});
    const result = calc.calculate(gen, a, d, move, new calc.Field(job.field));
    const [minimum, maximum] = result.range();
    if (![minimum, maximum].every(Number.isFinite)) throw Error('引擎没有返回有效范围');
    return {status:'ok', minimum, maximum, rolls:result.damage,
      percent_min:minimum*100/dRaw.hp, percent_max:maximum*100/dRaw.hp,
      max_hp:dRaw.hp, current_hp:job.defender.options.curHP || dRaw.hp,
      attacker_stats:aRaw, defender_stats:dRaw, details:result.rawDesc,
      note:'命中后本次直接伤害；百分比以最大 HP 为分母，不含后续回合与命中率'};
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
