"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Move = void 0;
exports.getZMoveName = getZMoveName;
exports.getMaxMoveName = getMaxMoveName;
const util_1 = require("./util");
const SPECIAL = ['Fire', 'Water', 'Grass', 'Electric', 'Ice', 'Psychic', 'Dark', 'Dragon'];
class Move {
    constructor(gen, name, options = {}) {
        var _a, _b;
        name = options.name || name;
        this.originalName = name;
        let data = (0, util_1.extend)(true, { name }, gen.moves.get((0, util_1.toID)(name)), options.overrides);
        this.hits = 1;
        if (options.useMax && data.maxMove) {
            // only useMax if the corresponding max move exists
            const maxMoveName = getMaxMoveName(gen, data.type, data.name, !!(data.category === 'Status'), options.ability, options.overrideMove);
            const maxMove = gen.moves.get((0, util_1.toID)(maxMoveName));
            const maxPower = () => {
                if (['G-Max Drum Solo', 'G-Max Fire Ball', 'G-Max Hydrosnipe'].includes(maxMoveName)) {
                    return 160;
                }
                // TODO: checking basePower === 10 is fragile (what if the maxMove's basePower is
                // overridden?) and also fails for Max Flare, which is strangely 100 BP in the game data
                if (maxMove.basePower === 10 || maxMoveName === 'Max Flare') {
                    return data.maxMove.basePower;
                }
                return maxMove.basePower;
            };
            data = (0, util_1.extend)(true, {}, maxMove, {
                name: maxMoveName,
                basePower: maxPower(),
                category: data.category,
            });
        }
        if (options.useZ && ((_a = data.zMove) === null || _a === void 0 ? void 0 : _a.basePower)) {
            // only useZ if the corresponding Z-Move exists
            const zMoveName = getZMoveName(data.name, data.type, options.item);
            const zMove = gen.moves.get((0, util_1.toID)(zMoveName));
            data = (0, util_1.extend)(true, {}, zMove, {
                name: zMoveName,
                basePower: zMove.basePower === 1 ? data.zMove.basePower : zMove.basePower,
                category: data.category,
            });
        }
        else {
            if (data.multihit) {
                if (data.multiaccuracy && typeof data.multihit === 'number') {
                    this.hits = options.hits || data.multihit;
                }
                else {
                    if (typeof data.multihit === 'number') {
                        this.hits = data.multihit;
                    }
                    else if (options.hits) {
                        this.hits = options.hits;
                    }
                    else {
                        this.hits = (options.ability === 'Skill Link')
                            ? data.multihit[1]
                            : data.multihit[0] + 1;
                    }
                }
            }
            this.timesUsedWithMetronome = options.timesUsedWithMetronome;
        }
        this.gen = gen;
        this.name = data.name;
        this.ability = options.ability;
        this.item = options.item;
        this.useZ = options.useZ;
        this.useMax = options.useMax;
        this.overrideMove = options.overrideMove;
        this.overrides = options.overrides;
        this.bp = data.basePower;
        // These moves have a type, but the damage they deal is typeless so we override it
        const typelessDamage = ((gen.num === 0 || gen.num >= 2) && data.id === 'struggle') ||
            ((gen.num > 0 && gen.num <= 4) && ['futuresight', 'doomdesire'].includes(data.id));
        this.type = typelessDamage ? '???' : data.type;
        this.category = data.category ||
            (gen.num > 0 && gen.num < 4
                ? (SPECIAL.includes(data.type) ? 'Special' : 'Physical')
                : 'Status');
        const stat = this.category === 'Special' ? 'spa' : 'atk';
        if (((_b = data.self) === null || _b === void 0 ? void 0 : _b.boosts) && data.self.boosts[stat] && data.self.boosts[stat] < 0) {
            this.dropsStats = Math.abs(data.self.boosts[stat]);
        }
        this.timesUsed = options.timesUsed || 1;
        this.secondaries = data.secondaries;
        // For the purposes of the damage formula only 'allAdjacent' and 'allAdjacentFoes' matter, so we
        // simply default to 'any' for the others even though they may not actually be 'any'-target
        this.target = data.target || 'any';
        this.recoil = data.recoil;
        this.hasCrashDamage = !!data.hasCrashDamage;
        this.mindBlownRecoil = !!data.mindBlownRecoil;
        this.struggleRecoil = !!data.struggleRecoil;
        this.isCrit = !!options.isCrit || !!data.willCrit ||
            // These don't *always* crit (255/256 chance), but for the purposes of the calc they do
            gen.num === 1 && ['crabhammer', 'razorleaf', 'slash', 'karate chop'].includes(data.id);
        this.isStellarFirstUse = !!options.isStellarFirstUse;
        this.drain = data.drain;
        this.flags = data.flags;
        // The calc doesn't currently care about negative priority moves so we simply default to 0
        this.priority = data.priority || 0;
        this.ignoreDefensive = !!data.ignoreDefensive;
        this.overrideOffensiveStat = data.overrideOffensiveStat;
        this.overrideDefensiveStat = data.overrideDefensiveStat;
        this.overrideOffensivePokemon = data.overrideOffensivePokemon;
        this.overrideDefensivePokemon = data.overrideDefensivePokemon;
        this.breaksProtect = !!data.breaksProtect;
        this.isZ = !!data.isZ;
        this.isMax = !!data.isMax;
        this.multiaccuracy = !!data.multiaccuracy;
        if (!this.bp) {
            // Assume max happiness for these moves because the calc doesn't support happiness
            if (['return', 'frustration', 'pikapapow', 'veeveevolley'].includes(data.id)) {
                this.bp = 102;
            }
        }
    }
    named(...names) {
        return names.includes(this.name);
    }
    hasType(...types) {
        return types.includes(this.type);
    }
    clone() {
        return new Move(this.gen, this.originalName, {
            ability: this.ability,
            item: this.item,
            useZ: this.useZ,
            useMax: this.useMax,
            overrideMove: this.overrideMove,
            isCrit: this.isCrit,
            isStellarFirstUse: this.isStellarFirstUse,
            hits: this.hits,
            timesUsed: this.timesUsed,
            timesUsedWithMetronome: this.timesUsedWithMetronome,
            overrides: this.overrides,
        });
    }
}
exports.Move = Move;
function getZMoveName(moveName, moveType, item) {
    item = item || '';
    if (moveName.includes('Hidden Power'))
        return 'Breakneck Blitz';
    if (moveName === 'Clanging Scales' && item === 'Kommonium Z')
        return 'Clangorous Soulblaze';
    if (moveName === 'Darkest Lariat' && item === 'Incinium Z')
        return 'Malicious Moonsault';
    if (moveName === 'Giga Impact' && item === 'Snorlium Z')
        return 'Pulverizing Pancake';
    if (moveName === 'Moongeist Beam' && item === 'Lunalium Z')
        return 'Menacing Moonraze Maelstrom';
    if (moveName === 'Photon Geyser' && item === 'Ultranecrozium Z') {
        return 'Light That Burns the Sky';
    }
    if (moveName === 'Play Rough' && item === 'Mimikium Z')
        return 'Let\'s Snuggle Forever';
    if (moveName === 'Psychic' && item === 'Mewnium Z')
        return 'Genesis Supernova';
    if (moveName === 'Sparkling Aria' && item === 'Primarium Z')
        return 'Oceanic Operetta';
    if (moveName === 'Spectral Thief' && item === 'Marshadium Z') {
        return 'Soul-Stealing 7-Star Strike';
    }
    if (moveName === 'Spirit Shackle' && item === 'Decidium Z')
        return 'Sinister Arrow Raid';
    if (moveName === 'Stone Edge' && item === 'Lycanium Z')
        return 'Splintered Stormshards';
    if (moveName === 'Sunsteel Strike' && item === 'Solganium Z')
        return 'Searing Sunraze Smash';
    if (moveName === 'Volt Tackle' && item === 'Pikanium Z')
        return 'Catastropika';
    if (moveName === 'Nature\'s Madness' && item === 'Tapunium Z')
        return 'Guardian of Alola';
    if (moveName === 'Thunderbolt') {
        if (item === 'Aloraichium Z')
            return 'Stoked Sparksurfer';
        if (item === 'Pikashunium Z')
            return '10,000,000 Volt Thunderbolt';
    }
    return ZMOVES_TYPING[moveType];
}
const ZMOVES_TYPING = {
    Bug: 'Savage Spin-Out',
    Dark: 'Black Hole Eclipse',
    Dragon: 'Devastating Drake',
    Electric: 'Gigavolt Havoc',
    Fairy: 'Twinkle Tackle',
    Fighting: 'All-Out Pummeling',
    Fire: 'Inferno Overdrive',
    Flying: 'Supersonic Skystrike',
    Ghost: 'Never-Ending Nightmare',
    Grass: 'Bloom Doom',
    Ground: 'Tectonic Rage',
    Ice: 'Subzero Slammer',
    Normal: 'Breakneck Blitz',
    Poison: 'Acid Downpour',
    Psychic: 'Shattered Psyche',
    Rock: 'Continental Crush',
    Steel: 'Corkscrew Crash',
    Water: 'Hydro Vortex',
};
function getMaxMoveName(gen, moveType, moveName, isStatus, pokemonAbility, isGmax) {
    if (isStatus)
        return 'Max Guard';
    if (pokemonAbility === 'Normalize')
        moveType = 'Normal';
    if (moveType === 'Normal' && !(moveName === 'Weather Ball' || moveName === 'Terrain Pulse')) {
        if (pokemonAbility === 'Pixilate')
            moveType = 'Fairy';
        if (pokemonAbility === 'Aerilate')
            moveType = 'Flying';
        if (pokemonAbility === 'Refrigerate')
            moveType = 'Ice';
        if (pokemonAbility === 'Galvanize')
            moveType = 'Electric';
    }
    if (isGmax && moveType === gen.moves.get((0, util_1.toID)(isGmax)).type) {
        return isGmax;
    }
    return 'Max ' + MAXMOVES_TYPING[moveType];
}
const MAXMOVES_TYPING = {
    Bug: 'Flutterby',
    Dark: 'Darkness',
    Dragon: 'Wyrmwind',
    Electric: 'Lightning',
    Fairy: 'Starfall',
    Fighting: 'Knuckle',
    Fire: 'Flare',
    Flying: 'Airstream',
    Ghost: 'Phantasm',
    Grass: 'Overgrowth',
    Ground: 'Quake',
    Ice: 'Hailstorm',
    Normal: 'Strike',
    Poison: 'Ooze',
    Psychic: 'Mindstorm',
    Rock: 'Rockfall',
    Steel: 'Steelspike',
    Water: 'Geyser',
};
