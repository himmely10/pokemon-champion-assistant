"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.calculateChampions = calculateChampions;
exports.calculateBasePowerChampions = calculateBasePowerChampions;
exports.calculateBPModsChampions = calculateBPModsChampions;
exports.calculateAttackChampions = calculateAttackChampions;
exports.calculateAtModsChampions = calculateAtModsChampions;
exports.calculateDefenseChampions = calculateDefenseChampions;
exports.calculateDfModsChampions = calculateDfModsChampions;
exports.calculateFinalModsChampions = calculateFinalModsChampions;
const util_1 = require("../util");
const items_1 = require("../items");
const result_1 = require("../result");
const util_2 = require("./util");
function calculateChampions(gen, attacker, defender, move, field) {
    // #region Initial
    (0, util_2.checkAirLock)(attacker, field);
    (0, util_2.checkAirLock)(defender, field);
    (0, util_2.checkForecast)(attacker, field.weather);
    (0, util_2.checkForecast)(defender, field.weather);
    (0, util_2.checkItem)(attacker, field.isMagicRoom);
    (0, util_2.checkItem)(defender, field.isMagicRoom);
    (0, util_2.checkRawStatChanges)(attacker, field.attackerSide.isPowerTrick, field.isWonderRoom);
    (0, util_2.checkRawStatChanges)(defender, field.defenderSide.isPowerTrick, field.isWonderRoom);
    (0, util_2.checkSeedBoost)(attacker, field);
    (0, util_2.checkSeedBoost)(defender, field);
    (0, util_2.computeFinalStats)(gen, attacker, defender, field, 'def', 'spd', 'spe');
    (0, util_2.checkIntimidate)(gen, attacker, defender);
    (0, util_2.checkIntimidate)(gen, defender, attacker);
    if (move.named('Meteor Beam', 'Electro Shot')) {
        attacker.boosts.spa += attacker.hasAbility('Contrary') ? -1 : 1;
        // restrict to +- 6
        attacker.boosts.spa = Math.min(6, Math.max(-6, attacker.boosts.spa));
    }
    (0, util_2.computeFinalStats)(gen, attacker, defender, field, 'atk', 'spa');
    (0, util_2.checkInfiltrator)(attacker, field.defenderSide);
    (0, util_2.checkInfiltrator)(defender, field.attackerSide);
    const desc = {
        attackerName: attacker.name,
        moveName: move.name,
        defenderName: defender.name,
        isWonderRoom: field.isWonderRoom,
    };
    const result = new result_1.Result(gen, attacker, defender, move, field, 0, desc);
    if (move.category === 'Status') {
        return result;
    }
    if (move.named('Shell Side Arm') &&
        (0, util_2.getShellSideArmCategory)(attacker, defender, field.isWonderRoom) === 'Physical') {
        move.category = 'Physical';
        move.flags.contact = 1;
    }
    const breaksProtect = move.breaksProtect ||
        (attacker.hasAbility('Unseen Fist', 'Piercing Drill') && move.flags.contact);
    if (field.defenderSide.isProtected && !breaksProtect) {
        desc.isProtected = true;
        return result;
    }
    if (move.name === 'Pain Split') {
        const average = Math.floor((attacker.curHP() + defender.curHP()) / 2);
        const damage = Math.max(0, defender.curHP() - average);
        result.damage = damage;
        return result;
    }
    const defenderAbilityIgnored = defender.hasAbility('Aura Guard', 'Armor Tail', 'Aroma Veil', 'Battle Armor', 'Big Pecks', 'Bulletproof', 'Clear Body', 'Contrary', 'Damp', 'Disguise', 'Dry Skin', 'Earth Eater', 'Eelevate', 'Filter', 'Flash Fire', 'Flower Veil', 'Fluffy', 'Friend Guard', 'Fur Coat', 'Grass Pelt', 'Guard Dog', 'Heatproof', 'Heavy Metal', 'Hyper Cutter', 'Illuminate', 'Immunity', 'Inner Focus', 'Insomnia', 'Keen Eye', 'Leaf Guard', 'Levitate', 'Light Metal', 'Lightning Rod', 'Limber', 'Magic Bounce', 'Magma Armor', 'Marvel Scale', 'Mirror Armor', 'Motor Drive', 'Multiscale', 'Oblivious', 'Overcoat', 'Own Tempo', 'Punk Rock', 'Purifying Salt', 'Queenly Majesty', 'Sand Veil', 'Sap Sipper', 'Shell Armor', 'Shield Dust', 'Snow Cloak', 'Solid Rock', 'Soundproof', 'Sticky Hold', 'Storm Drain', 'Sturdy', 'Sweet Veil', 'Tangled Feet', 'Telepathy', 'Thermal Exchange', 'Thick Fat', 'Unaware', 'Vital Spirit', 'Volt Absorb', 'Water Absorb', 'Water Bubble', 'Water Veil', 'White Smoke');
    const attackerIgnoresAbility = attacker.hasAbility('Mold Breaker');
    if (defenderAbilityIgnored && attackerIgnoresAbility) {
        if (attackerIgnoresAbility)
            desc.attackerAbility = attacker.ability;
        defender.ability = '';
    }
    // Merciless does not ignore Shell Armor, damage dealt to a poisoned Pokemon with Shell Armor
    // will not be a critical hit (UltiMario)
    const isCritical = !defender.hasAbility('Shell Armor', 'Battle Armor') &&
        (move.isCrit || (attacker.hasAbility('Merciless') && (defender.hasStatus('psn', 'tox') || attacker.abilityOn))) &&
        move.timesUsed === 1;
    let type = move.type;
    if (move.originalName === 'Weather Ball') {
        const isMegaSol = attacker.hasAbility('Mega Sol');
        type =
            field.hasWeather('Sun', 'Harsh Sunshine') || isMegaSol ? 'Fire'
                : field.hasWeather('Rain', 'Heavy Rain') ? 'Water'
                    : field.hasWeather('Sand') ? 'Rock'
                        : field.hasWeather('Hail', 'Snow') ? 'Ice'
                            : 'Normal';
        isMegaSol ? desc.attackerAbility = attacker.ability : desc.weather = field.weather;
        desc.moveType = type;
    }
    else if (move.originalName === 'Terrain Pulse' && (0, util_2.isGrounded)(attacker, field)) {
        type =
            field.hasTerrain('Electric') ? 'Electric'
                : field.hasTerrain('Grassy') ? 'Grass'
                    : field.hasTerrain('Misty') ? 'Fairy'
                        : field.hasTerrain('Psychic') ? 'Psychic'
                            : 'Normal';
        desc.terrain = field.terrain;
        // If the Nature Power user has the ability Prankster, it cannot affect
        // Dark-types or grounded foes if Psychic Terrain is active
        if (!(move.named('Nature Power') && attacker.hasAbility('Prankster')) &&
            ((defender.types.includes('Dark') ||
                (field.hasTerrain('Psychic') && (0, util_2.isGrounded)(defender, field))))) {
            desc.moveType = type;
        }
    }
    else if (move.named('Aura Wheel')) {
        if (attacker.named('Morpeko')) {
            type = 'Electric';
        }
        else if (attacker.named('Morpeko-Hangry')) {
            type = 'Dark';
        }
    }
    else if (move.named('Raging Bull')) {
        if (attacker.named('Tauros-Paldea-Combat')) {
            type = 'Fighting';
        }
        else if (attacker.named('Tauros-Paldea-Blaze')) {
            type = 'Fire';
        }
        else if (attacker.named('Tauros-Paldea-Aqua')) {
            type = 'Water';
        }
        field.defenderSide.isReflect = false;
        field.defenderSide.isLightScreen = false;
        field.defenderSide.isAuroraVeil = false;
    }
    else if (move.named('Brick Break', 'Psychic Fangs')) {
        field.defenderSide.isReflect = false;
        field.defenderSide.isLightScreen = false;
        field.defenderSide.isAuroraVeil = false;
    }
    if (attacker.hasAbility('Electromorphosis') && attacker.abilityOn) {
        field.attackerSide.isCharge = true;
    }
    let hasAteAbilityTypeChange = false;
    let isAerilate = false;
    let isDragonize = false;
    let isPixilate = false;
    let isRefrigerate = false;
    let isLiquidVoice = false;
    const noTypeChange = move.named('Weather Ball', 'Terrain Pulse', 'Struggle');
    if (!noTypeChange) {
        const normal = type === 'Normal';
        if ((isAerilate = attacker.hasAbility('Aerilate') && normal)) {
            type = 'Flying';
        }
        else if ((isDragonize = attacker.hasAbility('Dragonize') && normal)) {
            type = 'Dragon';
        }
        else if ((isLiquidVoice = attacker.hasAbility('Liquid Voice') && !!move.flags.sound)) {
            type = 'Water';
        }
        else if ((isPixilate = attacker.hasAbility('Pixilate') && normal)) {
            type = 'Fairy';
        }
        else if ((isRefrigerate = attacker.hasAbility('Refrigerate') && normal)) {
            type = 'Ice';
        }
        if (isAerilate || isDragonize || isPixilate || isRefrigerate) {
            desc.attackerAbility = attacker.ability;
            hasAteAbilityTypeChange = true;
        }
        else if (isLiquidVoice) {
            desc.attackerAbility = attacker.ability;
        }
    }
    move.type = type;
    // Priority changes must be resolved before priority-blocking abilities and
    // Psychic Terrain are checked below.
    if (move.named('Grassy Glide') && field.hasTerrain('Grassy') && (0, util_2.isGrounded)(attacker, field)) {
        move.priority = 1;
        desc.terrain = field.terrain;
    }
    if (attacker.hasAbility('Gale Wings') && move.hasType('Flying') &&
        (attacker.curHP() === attacker.maxHP() || attacker.abilityOn)) {
        move.priority += 1;
        desc.attackerAbility = attacker.ability;
    }
    const isGhostRevealed = attacker.hasAbility('Scrappy');
    const type1Effectiveness = (0, util_2.getMoveEffectiveness)(gen, move, defender.types[0], isGhostRevealed, field.isGravity, false);
    const type2Effectiveness = defender.types[1]
        ? (0, util_2.getMoveEffectiveness)(gen, move, defender.types[1], isGhostRevealed, field.isGravity, false)
        : 1;
    let typeEffectiveness = type1Effectiveness * type2Effectiveness;
    if (typeEffectiveness === 0 && move.hasType('Ground') &&
        defender.hasItem('Iron Ball') && !defender.hasAbility('Klutz')) {
        typeEffectiveness = 1;
    }
    if (typeEffectiveness === 0) {
        return result;
    }
    if ((move.named('Steel Roller') && !field.terrain) ||
        (move.named('Poltergeist') && !defender.item)) {
        return result;
    }
    if ((move.hasType('Grass') && defender.hasAbility('Sap Sipper')) ||
        (move.hasType('Fire') && defender.hasAbility('Flash Fire')) ||
        (move.hasType('Water') && defender.hasAbility('Dry Skin', 'Water Absorb')) ||
        (move.hasType('Electric') &&
            defender.hasAbility('Lightning Rod', 'Motor Drive', 'Volt Absorb')) ||
        (move.hasType('Ground') &&
            !field.isGravity && defender.hasAbility('Levitate', 'Eelevate')) ||
        (move.flags.bullet && defender.hasAbility('Bulletproof')) ||
        (move.flags.sound && !move.named('Clangorous Soul') && defender.hasAbility('Soundproof')) ||
        (move.priority > 0 && defender.hasAbility('Queenly Majesty', 'Armor Tail')) ||
        (move.hasType('Ground') && defender.hasAbility('Earth Eater'))) {
        desc.defenderAbility = defender.ability;
        return result;
    }
    if (move.hasType('Ground') && !field.isGravity && defender.hasItem('Air Balloon')) {
        desc.defenderItem = defender.item;
        return result;
    }
    if (move.priority > 0 && field.hasTerrain('Psychic') && (0, util_2.isGrounded)(defender, field)) {
        desc.terrain = field.terrain;
        return result;
    }
    desc.HPEVs = (0, util_2.getStatDescriptionText)(gen, defender, 'hp');
    const fixedDamage = (0, util_2.handleFixedDamageMoves)(attacker, move);
    if (fixedDamage) {
        if (attacker.hasAbility('Parental Bond')) {
            result.damage = [fixedDamage, fixedDamage];
            desc.attackerAbility = attacker.ability;
        }
        else {
            result.damage = fixedDamage;
        }
        return result;
    }
    if (move.named('Final Gambit')) {
        result.damage = attacker.curHP();
        return result;
    }
    if (move.hits > 1) {
        desc.hits = move.hits;
    }
    const turnOrder = attacker.stats.spe > defender.stats.spe ? 'first' : 'last';
    // #endregion
    // #region Base Power
    const basePower = calculateBasePowerChampions(gen, attacker, defender, move, field, hasAteAbilityTypeChange, desc);
    if (basePower === 0) {
        return result;
    }
    // #endregion
    // #region (Special) Attack
    const attack = calculateAttackChampions(gen, attacker, defender, move, field, desc, isCritical);
    // #endregion
    // #region (Special) Defense
    const defense = calculateDefenseChampions(gen, attacker, defender, move, field, desc, isCritical);
    const hitsPhysical = move.overrideDefensiveStat === 'def' || move.category === 'Physical';
    const defenseStat = hitsPhysical ? 'def' : 'spd';
    // #endregion
    // #region Damage
    const baseDamage = calculateBaseDamageChampions(gen, attacker, defender, basePower, attack, defense, move, field, desc, isCritical);
    if (hasTerrainSeed(defender) &&
        field.hasTerrain(defender.item.substring(0, defender.item.indexOf(' '))) &&
        items_1.SEED_BOOSTED_STAT[defender.item] === defenseStat) {
        // Last condition applies so the calc doesn't show a seed where it wouldn't affect the outcome
        // (like Grassy Seed when being hit by a special move)
        desc.defenderItem = defender.item;
    }
    // the random factor is applied between the crit mod and the stab mod, so don't apply anything
    // below this until we're inside the loop
    let stabMod = (0, util_2.getStabMod)(attacker, move, desc);
    const applyBurn = attacker.hasStatus('brn') &&
        move.category === 'Physical' &&
        !attacker.hasAbility('Guts') &&
        !move.named('Facade');
    desc.isBurned = applyBurn;
    const finalMods = calculateFinalModsChampions(gen, attacker, defender, move, field, desc, isCritical, typeEffectiveness);
    let protect = false;
    if (field.defenderSide.isProtected &&
        (attacker.hasAbility('Unseen Fist', 'Piercing Drill') && move.flags.contact)) {
        protect = true;
        desc.isProtected = true;
    }
    const finalMod = (0, util_2.chainMods)(finalMods, 41, 131072);
    const isSpread = field.gameType !== 'Singles' && !field.isSingleTarget &&
        ['allAdjacent', 'allAdjacentFoes'].includes(move.target);
    let childDamage;
    if (attacker.hasAbility('Parental Bond') && move.hits === 1 && !isSpread) {
        const child = attacker.clone();
        child.ability = 'Parental Bond (Child)';
        (0, util_2.checkMultihitBoost)(gen, child, defender, move, field, desc);
        childDamage = calculateChampions(gen, child, defender, move, field).damage;
        desc.attackerAbility = attacker.ability;
    }
    const damage = [];
    for (let i = 0; i < 16; i++) {
        damage[i] =
            (0, util_2.getFinalDamage)(baseDamage, i, typeEffectiveness, applyBurn, stabMod, finalMod, protect);
    }
    result.damage = childDamage ? [damage, childDamage] : damage;
    if (move.timesUsed > 1 || move.hits > 1) {
        // store boosts so intermediate boosts don't show.
        const origDefBoost = desc.defenseBoost;
        const origAtkBoost = desc.attackBoost;
        let numAttacks = 1;
        if (move.timesUsed > 1) {
            desc.moveTurns = `over ${move.timesUsed} turns`;
            numAttacks = move.timesUsed;
        }
        else {
            numAttacks = move.hits;
        }
        let usedItems = [false, false];
        const damageMatrix = [damage];
        for (let times = 1; times < numAttacks; times++) {
            usedItems = (0, util_2.checkMultihitBoost)(gen, attacker, defender, move, field, desc, usedItems[0], usedItems[1]);
            const newAttack = calculateAttackChampions(gen, attacker, defender, move, field, desc, isCritical);
            const newDefense = calculateDefenseChampions(gen, attacker, defender, move, field, desc, isCritical);
            // Check if lost -ate ability. Typing stays the same, only boost is lost
            // Cannot be regained during multihit move and no Normal moves with stat drawbacks
            hasAteAbilityTypeChange = hasAteAbilityTypeChange &&
                attacker.hasAbility('Aerilate', 'Dragonize', 'Pixilate', 'Refrigerate');
            if (move.timesUsed > 1) {
                stabMod = (0, util_2.getStabMod)(attacker, move, desc);
            }
            const newBasePower = calculateBasePowerChampions(gen, attacker, defender, move, field, hasAteAbilityTypeChange, desc, times + 1);
            const newBaseDamage = calculateBaseDamageChampions(gen, attacker, defender, newBasePower, newAttack, newDefense, move, field, desc, isCritical);
            const newFinalMods = calculateFinalModsChampions(gen, attacker, defender, move, field, desc, isCritical, typeEffectiveness, times);
            const newFinalMod = (0, util_2.chainMods)(newFinalMods, 41, 131072);
            const damageArray = [];
            for (let i = 0; i < 16; i++) {
                const newFinalDamage = (0, util_2.getFinalDamage)(newBaseDamage, i, typeEffectiveness, applyBurn, stabMod, newFinalMod, protect);
                damageArray[i] = newFinalDamage;
            }
            damageMatrix[times] = damageArray;
        }
        result.damage = damageMatrix;
        desc.defenseBoost = origDefBoost;
        desc.attackBoost = origAtkBoost;
    }
    // #endregion
    return result;
}
function calculateBasePowerChampions(gen, attacker, defender, move, field, hasAteAbilityTypeChange, desc, hit = 1) {
    const turnOrder = attacker.stats.spe > defender.stats.spe ? 'first' : 'last';
    let basePower;
    switch (move.name) {
        case 'Payback':
            basePower = move.bp * (turnOrder === 'last' ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Electro Ball':
            const r = Math.floor(attacker.stats.spe / defender.stats.spe);
            basePower = r >= 4 ? 150 : r >= 3 ? 120 : r >= 2 ? 80 : r >= 1 ? 60 : 40;
            if (defender.stats.spe === 0)
                basePower = 40;
            desc.moveBP = basePower;
            break;
        case 'Gyro Ball':
            basePower = Math.min(150, Math.floor((25 * defender.stats.spe) / attacker.stats.spe) + 1);
            if (attacker.stats.spe === 0)
                basePower = 1;
            desc.moveBP = basePower;
            break;
        case 'Punishment':
            basePower = Math.min(200, 60 + 20 * (0, util_2.countBoosts)(gen, defender.boosts));
            desc.moveBP = basePower;
            break;
        case 'Low Kick':
        case 'Grass Knot':
            const w = (0, util_2.getWeight)(defender, desc, 'defender');
            basePower = w >= 200 ? 120 : w >= 100 ? 100 : w >= 50 ? 80 : w >= 25 ? 60 : w >= 10 ? 40 : 20;
            desc.moveBP = basePower;
            break;
        case 'Hex':
        case 'Infernal Parade':
            basePower = move.bp * (defender.status ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Barb Barrage':
            basePower = move.bp * (defender.hasStatus('psn', 'tox') ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Heavy Slam':
        case 'Heat Crash':
            const wr = (0, util_2.getWeight)(attacker, desc, 'attacker') /
                (0, util_2.getWeight)(defender, desc, 'defender');
            basePower = wr >= 5 ? 120 : wr >= 4 ? 100 : wr >= 3 ? 80 : wr >= 2 ? 60 : 40;
            desc.moveBP = basePower;
            break;
        case 'Stored Power':
        case 'Power Trip':
            basePower = 20 + 20 * (0, util_2.countBoosts)(gen, attacker.boosts);
            desc.moveBP = basePower;
            break;
        case 'Acrobatics':
            basePower = move.bp * (!attacker.item ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Assurance':
            basePower = move.bp * (defender.hasAbility('Parental Bond (Child)') ? 2 : 1);
            // NOTE: desc.attackerAbility = 'Parental Bond' will already reflect this boost
            break;
        case 'Smelling Salts':
            basePower = move.bp * (defender.hasStatus('par') ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Weather Ball':
            basePower = move.bp * (field.weather || attacker.hasAbility('Mega Sol') ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Terrain Pulse':
            basePower = move.bp * ((0, util_2.isGrounded)(attacker, field) && field.terrain ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Rising Voltage':
            basePower = move.bp * (((0, util_2.isGrounded)(defender, field) && field.hasTerrain('Electric')) ? 2 : 1);
            desc.moveBP = basePower;
            break;
        case 'Fling':
            basePower = (0, items_1.getFlingPower)(attacker.item, gen.num);
            desc.moveBP = basePower;
            desc.attackerItem = attacker.item;
            break;
        case 'Eruption':
        case 'Water Spout':
            basePower = Math.max(1, Math.floor((150 * attacker.curHP()) / attacker.maxHP()));
            desc.moveBP = basePower;
            break;
        case 'Flail':
        case 'Reversal':
            const p = Math.floor((48 * attacker.curHP()) / attacker.maxHP());
            basePower = p <= 1 ? 200 : p <= 4 ? 150 : p <= 9 ? 100 : p <= 16 ? 80 : p <= 32 ? 40 : 20;
            desc.moveBP = basePower;
            break;
        // Triple Axel's damage increases after each consecutive hit (20, 40, 60)
        case 'Triple Axel':
            basePower = hit * 20;
            desc.moveBP = move.hits === 2 ? 60 : move.hits === 3 ? 120 : 20;
            break;
        case 'Hard Press':
            basePower = 100 * Math.floor((defender.curHP() * 4096) / defender.maxHP());
            basePower = Math.floor(Math.floor((100 * basePower + 2048 - 1) / 4096) / 100) || 1;
            desc.moveBP = basePower;
            break;
        default:
            basePower = move.bp;
    }
    if (basePower === 0) {
        return 0;
    }
    const bpMods = calculateBPModsChampions(gen, attacker, defender, move, field, desc, basePower, hasAteAbilityTypeChange, turnOrder, hit);
    basePower = (0, util_2.OF16)(Math.max(1, (0, util_2.pokeRound)((basePower * (0, util_2.chainMods)(bpMods, 41, 2097152)) / 4096)));
    return basePower;
}
function calculateBPModsChampions(gen, attacker, defender, move, field, desc, basePower, hasAteAbilityTypeChange, turnOrder, hit) {
    const bpMods = [];
    // Move effects
    const defenderItem = (defender.item && defender.item !== '')
        ? defender.item : defender.disabledItem;
    let resistedKnockOffDamage = !defenderItem;
    // The last case only applies when the Pokemon has the Mega Stone that matches its species
    // (or when it's already a Mega-Evolution)
    if (!resistedKnockOffDamage && defenderItem) {
        const item = gen.items.get((0, util_1.toID)(defenderItem));
        resistedKnockOffDamage = !!(item.megaStone &&
            (item.megaStone[defender.name] || Object.values(item.megaStone).includes(defender.name)));
    }
    // Resist knock off damage if your item was already knocked off
    if (!resistedKnockOffDamage && hit > 1 && !defender.hasAbility('Sticky Hold')) {
        resistedKnockOffDamage = true;
    }
    // Move effects
    if ((move.named('Facade') && attacker.hasStatus('brn', 'par', 'psn', 'tox')) ||
        (move.named('Venoshock') && defender.hasStatus('psn', 'tox')) ||
        (move.named('Lash Out') && ((0, util_2.countBoosts)(gen, attacker.boosts) < 0))) {
        bpMods.push(8192);
        desc.moveBP = basePower * 2;
    }
    else if (move.named('Expanding Force') && (0, util_2.isGrounded)(attacker, field) && field.hasTerrain('Psychic')) {
        move.target = 'allAdjacentFoes';
        bpMods.push(6144);
        desc.moveBP = basePower * 1.5;
    }
    else if ((move.named('Knock Off') && !resistedKnockOffDamage) ||
        (move.named('Misty Explosion') && (0, util_2.isGrounded)(attacker, field) && field.hasTerrain('Misty')) ||
        (move.named('Grav Apple') && field.isGravity)) {
        bpMods.push(6144);
        desc.moveBP = basePower * 1.5;
    }
    else if (move.named('Solar Beam', 'Solar Blade') &&
        field.hasWeather('Rain', 'Sand', 'Hail', 'Snow') && !attacker.hasAbility('Mega Sol')) {
        bpMods.push(2048);
        desc.moveBP = basePower / 2;
        desc.weather = field.weather;
    }
    if (field.attackerSide.isHelpingHand) {
        bpMods.push(6144);
        desc.isHelpingHand = true;
    }
    // Field effects
    const terrainMultiplier = 5325;
    if ((0, util_2.isGrounded)(attacker, field)) {
        if ((field.hasTerrain('Electric') && move.hasType('Electric')) ||
            (field.hasTerrain('Grassy') && move.hasType('Grass')) ||
            (field.hasTerrain('Psychic') && move.hasType('Psychic'))) {
            bpMods.push(terrainMultiplier);
            desc.terrain = field.terrain;
        }
    }
    if ((0, util_2.isGrounded)(defender, field)) {
        if ((field.hasTerrain('Misty') && move.hasType('Dragon')) ||
            (field.hasTerrain('Grassy') && move.named('Bulldoze', 'Earthquake'))) {
            bpMods.push(2048);
            desc.terrain = field.terrain;
        }
    }
    // Abilities
    // Use BasePower after moves with custom BP to determine if Technician should boost
    if ((attacker.hasAbility('Technician') && basePower <= 60) ||
        (attacker.hasAbility('Mega Launcher') && move.flags.pulse) ||
        (attacker.hasAbility('Strong Jaw') && move.flags.bite) ||
        (attacker.hasAbility('Steely Spirit') && move.hasType('Steel')) ||
        (attacker.hasAbility('Sharpness') && move.flags.slicing)) {
        bpMods.push(6144);
        desc.attackerAbility = attacker.ability;
    }
    if (field.attackerSide.isCharge && move.hasType('Electric')) {
        bpMods.push(8192);
        desc.isCharge = true;
    }
    const aura = `${move.type} Aura`;
    const isAttackerAura = attacker.hasAbility(aura);
    const isDefenderAura = defender.hasAbility(aura);
    const isFieldFairyAura = field.isFairyAura && move.type === 'Fairy';
    const isFieldDarkAura = field.isDarkAura && move.type === 'Dark';
    const auraActive = isAttackerAura || isDefenderAura || isFieldFairyAura || isFieldDarkAura;
    if (auraActive) {
        bpMods.push(5448);
        if (isAttackerAura)
            desc.attackerAbility = attacker.ability;
        if (isDefenderAura)
            desc.defenderAbility = defender.ability;
    }
    if ((attacker.hasAbility('Sheer Force') &&
        (move.secondaries || move.named('Electro Shot')) ||
        (attacker.hasAbility('Sand Force') &&
            (field.hasWeather('Sand') || attacker.abilityOn) && move.hasType('Rock', 'Ground', 'Steel')) ||
        (attacker.hasAbility('Analytic') &&
            (turnOrder !== 'first' || field.defenderSide.isSwitching === 'out' || attacker.abilityOn)) ||
        (attacker.hasAbility('Tough Claws') && move.flags.contact)) ||
        (attacker.hasAbility('Punk Rock') && move.flags.sound)) {
        bpMods.push(5325);
        desc.attackerAbility = attacker.ability;
    }
    if (attacker.hasAbility('Rivalry') && (attacker.abilityOn || ![attacker.gender, defender.gender].includes('N'))) {
        if (attacker.abilityOn || attacker.gender === defender.gender) {
            bpMods.push(5120);
            desc.rivalry = 'buffed';
        }
        else {
            bpMods.push(3072);
            desc.rivalry = 'nerfed';
        }
        desc.attackerAbility = attacker.ability;
    }
    // The -ate abilities already changed move typing earlier, so most checks are done and desc is set
    if (hasAteAbilityTypeChange) {
        bpMods.push(4915);
    }
    if ((attacker.hasAbility('Reckless') && (move.recoil || move.hasCrashDamage)) ||
        (attacker.hasAbility('Iron Fist') && move.flags.punch)) {
        bpMods.push(4915);
        desc.attackerAbility = attacker.ability;
    }
    if (defender.hasAbility('Dry Skin') && move.hasType('Fire')) {
        bpMods.push(5120);
        desc.defenderAbility = defender.ability;
    }
    if (attacker.hasAbility('Supreme Overlord') && attacker.alliesFainted) {
        const powMod = [4096, 4506, 4915, 5325, 5734, 6144];
        bpMods.push(powMod[Math.min(5, attacker.alliesFainted)]);
        desc.attackerAbility = attacker.ability;
        desc.alliesFainted = attacker.alliesFainted;
    }
    // Items
    if (attacker.hasItem(`${move.type} Gem`)) {
        bpMods.push(5325);
        desc.attackerItem = attacker.item;
    }
    else if (attacker.item && move.hasType((0, items_1.getItemBoostType)(attacker.item))) {
        bpMods.push(4915);
        desc.attackerItem = attacker.item;
    }
    else if ((attacker.hasItem('Muscle Band') && move.category === 'Physical') ||
        (attacker.hasItem('Wise Glasses') && move.category === 'Special')) {
        bpMods.push(4505);
        desc.attackerItem = attacker.item;
    }
    return bpMods;
}
function calculateAttackChampions(gen, attacker, defender, move, field, desc, isCritical = false) {
    let attack;
    const attackSource = move.named('Foul Play') ? defender : attacker;
    const attackStat = move.named('Body Press')
        ? (field.isWonderRoom ? 'spd' : 'def')
        : (move.category === 'Special' ? 'spa' : 'atk');
    // Body Press in Wonder Room uses normal Def, which checkRawStatChanges has moved to SpD
    desc.attackEVs =
        move.named('Foul Play')
            ? (0, util_2.getStatDescriptionText)(gen, attackSource, attackStat, field.defenderSide.isPowerTrick)
            : (0, util_2.getStatDescriptionText)(gen, attackSource, attackStat, field.attackerSide.isPowerTrick, field.isWonderRoom);
    if (field.attackerSide.isPowerTrick) {
        if ((move.category === 'Physical' && !move.named('Foul Play')) || move.named('Body Press')) {
            desc.isPowerTrickAttacker = true;
        }
    }
    const boosts = attackSource.boosts[attackStat];
    if (boosts === 0 || (isCritical && boosts < 0)) {
        attack = attackSource.rawStats[attackStat];
    }
    else if (defender.hasAbility('Unaware')) {
        attack = attackSource.rawStats[attackStat];
        desc.defenderAbility = defender.ability;
    }
    else {
        attack = (0, util_2.getModifiedStat)(attackSource.rawStats[attackStat], boosts);
        desc.attackBoost = boosts;
    }
    // unlike all other attack modifiers, Hustle gets applied directly
    if (attacker.hasAbility('Hustle') && move.category === 'Physical') {
        attack = (0, util_2.pokeRound)((attack * 3) / 2);
        desc.attackerAbility = attacker.ability;
    }
    const atMods = calculateAtModsChampions(gen, attacker, defender, move, field, desc);
    attack = (0, util_2.OF16)(Math.max(1, (0, util_2.pokeRound)((attack * (0, util_2.chainMods)(atMods, 410, 131072)) / 4096)));
    return attack;
}
function calculateAtModsChampions(gen, attacker, defender, move, field, desc) {
    const atMods = [];
    if ((attacker.hasAbility('Solar Power') &&
        (field.hasWeather('Sun') || attacker.abilityOn) &&
        move.category === 'Special')) {
        atMods.push(6144);
        desc.attackerAbility = attacker.ability;
        desc.weather = field.weather;
    }
    else if ((attacker.hasAbility('Guts') && (attacker.status || attacker.abilityOn) && move.category === 'Physical') ||
        ((attacker.curHP() <= attacker.maxHP() / 3 || attacker.abilityOn) &&
            ((attacker.hasAbility('Overgrow') && move.hasType('Grass')) ||
                (attacker.hasAbility('Blaze') && move.hasType('Fire')) ||
                (attacker.hasAbility('Torrent') && move.hasType('Water')) ||
                (attacker.hasAbility('Swarm') && move.hasType('Bug')))) ||
        (move.category === 'Special' && attacker.abilityOn && attacker.hasAbility('Plus', 'Minus'))) {
        atMods.push(6144);
        desc.attackerAbility = attacker.ability;
    }
    else if (attacker.hasAbility('Flash Fire') && attacker.abilityOn && move.hasType('Fire')) {
        atMods.push(6144);
        desc.attackerAbility = 'Flash Fire';
    }
    else if (attacker.hasAbility('Fire Mane') && move.hasType('Fire')) {
        atMods.push(6144);
        desc.attackerAbility = attacker.ability;
    }
    else if ((attacker.hasAbility('Water Bubble') && move.hasType('Water')) ||
        (attacker.hasAbility('Huge Power', 'Pure Power') && move.category === 'Physical')) {
        atMods.push(8192);
        desc.attackerAbility = attacker.ability;
    }
    else if (attacker.hasAbility('Stakeout') && attacker.abilityOn) {
        atMods.push(8192);
        desc.attackerAbility = attacker.ability;
    }
    if ((defender.hasAbility('Thick Fat') && move.hasType('Fire', 'Ice')) ||
        (defender.hasAbility('Water Bubble') && move.hasType('Fire')) ||
        (defender.hasAbility('Purifying Salt') && move.hasType('Ghost'))) {
        atMods.push(2048);
        desc.defenderAbility = defender.ability;
    }
    if (defender.hasAbility('Heatproof') && move.hasType('Fire')) {
        atMods.push(2048);
        desc.defenderAbility = defender.ability;
    }
    if (attacker.hasItem('Light Ball') && attacker.name.includes('Pikachu')) {
        atMods.push(8192);
        desc.attackerItem = attacker.item;
    }
    return atMods;
}
function calculateDefenseChampions(gen, attacker, defender, move, field, desc, isCritical = false) {
    let defense;
    const hitsPhysical = move.overrideDefensiveStat === 'def' || move.category === 'Physical';
    const defenseStat = hitsPhysical ? 'def' : 'spd';
    desc.defenseEVs = (0, util_2.getStatDescriptionText)(gen, defender, defenseStat, field.defenderSide.isPowerTrick, field.isWonderRoom);
    if (field.defenderSide.isPowerTrick && (field.isWonderRoom !== hitsPhysical)) {
        desc.isPowerTrickDefender = true;
    }
    const boosts = defender.boosts[defenseStat];
    if (boosts === 0 ||
        (isCritical && boosts > 0) ||
        move.ignoreDefensive) {
        defense = defender.rawStats[defenseStat];
    }
    else if (attacker.hasAbility('Unaware')) {
        defense = defender.rawStats[defenseStat];
        desc.attackerAbility = attacker.ability;
    }
    else {
        defense = (0, util_2.getModifiedStat)(defender.rawStats[defenseStat], boosts);
        desc.defenseBoost = boosts;
    }
    // unlike all other defense modifiers, Sandstorm SpD boost gets applied directly
    if (!attacker.hasAbility('Mega Sol')) {
        if (field.hasWeather('Sand') && defender.hasType('Rock') && !hitsPhysical) {
            defense = (0, util_2.pokeRound)((defense * 3) / 2);
            desc.weather = field.weather;
        }
        if (field.hasWeather('Snow') && defender.hasType('Ice') && hitsPhysical) {
            defense = (0, util_2.pokeRound)((defense * 3) / 2);
            desc.weather = field.weather;
        }
    }
    const dfMods = calculateDfModsChampions(gen, attacker, defender, move, field, desc, isCritical, hitsPhysical);
    return (0, util_2.OF16)(Math.max(1, (0, util_2.pokeRound)((defense * (0, util_2.chainMods)(dfMods, 410, 131072)) / 4096)));
}
function calculateDfModsChampions(gen, attacker, defender, move, field, desc, isCritical = false, hitsPhysical = false) {
    const dfMods = [];
    if (defender.hasAbility('Marvel Scale') && (defender.status || defender.abilityOn) && hitsPhysical) {
        dfMods.push(6144);
        desc.defenderAbility = defender.ability;
    }
    else if (defender.hasAbility('Grass Pelt') &&
        (field.hasTerrain('Grassy') || defender.abilityOn) &&
        hitsPhysical) {
        dfMods.push(6144);
        desc.defenderAbility = defender.ability;
    }
    else if (defender.hasAbility('Fur Coat') && hitsPhysical) {
        dfMods.push(8192);
        desc.defenderAbility = defender.ability;
    }
    return dfMods;
}
function calculateBaseDamageChampions(gen, attacker, defender, basePower, attack, defense, move, field, desc, isCritical = false) {
    let baseDamage = (0, util_2.getBaseDamage)(attacker.level, basePower, attack, defense);
    const isSpread = field.gameType !== 'Singles' && !field.isSingleTarget &&
        ['allAdjacent', 'allAdjacentFoes'].includes(move.target);
    if (isSpread) {
        baseDamage = (0, util_2.pokeRound)((0, util_2.OF32)(baseDamage * 3072) / 4096);
    }
    if (attacker.hasAbility('Parental Bond (Child)')) {
        baseDamage = (0, util_2.pokeRound)((0, util_2.OF32)(baseDamage * 1024) / 4096);
    }
    const isMegaSol = attacker.hasAbility('Mega Sol');
    if (((field.hasWeather('Sun') || isMegaSol) && move.hasType('Fire')) ||
        ((field.hasWeather('Rain') && !isMegaSol) && move.hasType('Water'))) {
        baseDamage = (0, util_2.pokeRound)((0, util_2.OF32)(baseDamage * 6144) / 4096);
        isMegaSol ? desc.attackerAbility = attacker.ability : desc.weather = field.weather;
    }
    else if (((field.hasWeather('Sun') || isMegaSol) && move.hasType('Water')) ||
        (field.hasWeather('Rain') && move.hasType('Fire'))) {
        baseDamage = (0, util_2.pokeRound)((0, util_2.OF32)(baseDamage * 2048) / 4096);
        isMegaSol ? desc.attackerAbility = attacker.ability : desc.weather = field.weather;
    }
    if (isCritical) {
        baseDamage = Math.floor((0, util_2.OF32)(baseDamage * 1.5));
        desc.isCritical = isCritical;
    }
    return baseDamage;
}
function calculateFinalModsChampions(gen, attacker, defender, move, field, desc, isCritical = false, typeEffectiveness, hitCount = 0) {
    const finalMods = [];
    if (field.defenderSide.isReflect && move.category === 'Physical' &&
        !isCritical && !field.defenderSide.isAuroraVeil) {
        // doesn't stack with Aurora Veil
        finalMods.push(field.gameType !== 'Singles' ? 2732 : 2048);
        desc.isReflect = true;
    }
    else if (field.defenderSide.isLightScreen && move.category === 'Special' &&
        !isCritical && !field.defenderSide.isAuroraVeil) {
        // doesn't stack with Aurora Veil
        finalMods.push(field.gameType !== 'Singles' ? 2732 : 2048);
        desc.isLightScreen = true;
    }
    if (field.defenderSide.isAuroraVeil && !isCritical) {
        finalMods.push(field.gameType !== 'Singles' ? 2732 : 2048);
        desc.isAuroraVeil = true;
    }
    if (attacker.hasAbility('Sniper') && isCritical) {
        finalMods.push(6144);
        desc.attackerAbility = attacker.ability;
    }
    if (defender.hasAbility('Multiscale') &&
        (defender.curHP() === defender.maxHP() || defender.abilityOn) &&
        hitCount === 0 &&
        (!field.defenderSide.isSR && (!field.defenderSide.spikes || defender.hasType('Flying'))) &&
        !attacker.hasAbility('Parental Bond (Child)')) {
        finalMods.push(2048);
        desc.defenderAbility = defender.ability;
    }
    const halveContactMoveDmg = defender.hasAbility('Fluffy') ||
        (defender.hasAbility('Aura Guard') && move.category === 'Physical');
    if (halveContactMoveDmg && move.flags.contact && !attacker.hasAbility('Long Reach')) {
        finalMods.push(2048);
        desc.defenderAbility = defender.ability;
    }
    else if (defender.hasAbility('Punk Rock') && move.flags.sound) {
        finalMods.push(2048);
        desc.defenderAbility = defender.ability;
    }
    if (defender.hasAbility('Solid Rock', 'Filter') && typeEffectiveness > 1) {
        finalMods.push(3072);
        desc.defenderAbility = defender.ability;
    }
    if (field.defenderSide.isFriendGuard) {
        finalMods.push(3072);
        desc.isFriendGuard = true;
    }
    if (defender.hasAbility('Fluffy') && move.hasType('Fire')) {
        finalMods.push(8192);
        desc.defenderAbility = defender.ability;
    }
    if (attacker.hasItem('Expert Belt') && typeEffectiveness > 1) {
        finalMods.push(4915);
        desc.attackerItem = attacker.item;
    }
    else if (attacker.hasItem('Life Orb')) {
        finalMods.push(5324);
        desc.attackerItem = attacker.item;
    }
    else if (attacker.hasItem('Metronome') && move.timesUsedWithMetronome >= 1) {
        const timesUsedWithMetronome = Math.floor(move.timesUsedWithMetronome);
        if (timesUsedWithMetronome <= 4) {
            finalMods.push(4096 + timesUsedWithMetronome * 819);
        }
        else {
            finalMods.push(8192);
        }
        desc.attackerItem = attacker.item;
    }
    if (move.hasType((0, items_1.getBerryResistType)(defender.item)) &&
        (typeEffectiveness > 1 || move.hasType('Normal')) &&
        hitCount === 0 &&
        !attacker.hasAbility('Unnerve')) {
        if (defender.hasAbility('Ripen')) {
            finalMods.push(1024);
        }
        else {
            finalMods.push(2048);
        }
        desc.defenderItem = defender.item;
    }
    return finalMods;
}
function hasTerrainSeed(pokemon) {
    return pokemon.hasItem('Electric Seed', 'Misty Seed', 'Grassy Seed', 'Psychic Seed');
}
