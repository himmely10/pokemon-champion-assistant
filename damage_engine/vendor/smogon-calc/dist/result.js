"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Result = void 0;
exports.damageRange = damageRange;
exports.multiDamageRange = multiDamageRange;
const desc_1 = require("./desc");
class Result {
    constructor(gen, attacker, defender, move, field, damage, rawDesc) {
        this.gen = gen;
        this.attacker = attacker;
        this.defender = defender;
        this.move = move;
        this.field = field;
        this.damage = damage;
        this.rawDesc = rawDesc;
    }
    /* get */ desc() {
        return this.fullDesc();
    }
    range() {
        const [min, max] = damageRange(this.damage);
        return [min, max];
    }
    fullDesc(notation = '%', err = true) {
        return (0, desc_1.display)(this.gen, this.attacker, this.defender, this.move, this.field, this.damage, this.rawDesc, notation, err);
    }
    moveDesc(notation = '%') {
        return (0, desc_1.displayMove)(this.gen, this.attacker, this.defender, this.move, this.damage, notation);
    }
    recovery(notation = '%') {
        return (0, desc_1.getRecovery)(this.gen, this.attacker, this.defender, this.move, this.damage, notation);
    }
    recoil(notation = '%') {
        return (0, desc_1.getRecoil)(this.gen, this.attacker, this.defender, this.move, this.damage, notation);
    }
    kochance(err = true) {
        return (0, desc_1.getKOChance)(this.gen, this.attacker, this.defender, this.move, this.field, this.damage, err);
    }
}
exports.Result = Result;
function damageRange(damage) {
    const range = multiDamageRange(damage);
    if (typeof range[0] === 'number')
        return range;
    const d = range;
    const summedRange = [0, 0];
    for (let i = 0; i < d[0].length; i++) {
        summedRange[0] += d[0][i];
        summedRange[1] += d[1][i];
    }
    return summedRange;
}
function multiDamageRange(damage) {
    // Fixed Damage
    if (typeof damage === 'number')
        return [damage, damage];
    // Multihit Damage
    if (typeof damage[0] !== 'number') {
        damage = damage;
        const ranges = [[], []];
        for (const damageList of damage) {
            ranges[0].push(damageList[0]);
            ranges[1].push(damageList[damageList.length - 1]);
        }
        return ranges;
    }
    const d = damage;
    // Fixed Multihit
    if (d.length < 16) {
        return [d, d];
    }
    // Standard Damage
    return [d[0], d[d.length - 1]];
}
