"use strict";
// When using this library in the browser, a bundler like Webpack should be
// used to encapsulate the various interdependencies between internal packages.
// However, if you are requiring contents of this package in HTML <script>
// tags, the following loading order is required:
//
//   - util.js
//   - stats.js
//
//   - data/species.js
//   - data/types.js
//   - data/natures.js
//   - data/abilities.js
//   - data/moves.js
//   - data/items.js
//   - data/index.js
//
//   - pokemon.js
//   - field.js
//   - move.js
//   - items.js
//
//   - mechanics/util.js
//   - mechanics/gen789.js
//   - mechanics/gen56.js
//   - mechanics/gen4.js
//   - mechanics/gen3.js
//   - mechanics/gen12.js
//
//   - calc.js
//   - desc.js
//   - result.js
//
//   - adaptable.js
//   - index.js
//
// Furthermore, before anything is loaded, the following is required:
//
// <script type="text/javascript">
//		var calc = exports = {};
//		function require() { return exports; };
//	</script>
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.Stats = exports.STATS = exports.TYPE_CHART = exports.NATURES = exports.SPECIES = exports.MOVES = exports.MEGA_STONES = exports.ITEMS = exports.ABILITIES = exports.toID = exports.Generations = exports.Result = exports.Side = exports.Field = exports.Pokemon = exports.Move = void 0;
exports.calculate = calculate;
exports.calcStat = calcStat;
// If we're not being used as a module we're just going to rely on globals and
// that the correct loading order being followed.
const data_1 = require("./data");
const A = __importStar(require("./adaptable"));
// The loading strategy outlined in the comment above breaks in the browser when we start reusing
// names as we're doing here with our shim overrides. Because exporting calculate below tramples
// A.calculate, this ends up infinitely calling itself. As a workaround we save the original value
// of A.calculate (which would be exports.calculate if files are loaded as outlined above) so that
// we can call that instead.
//
// This is obviously kludge, use a bundler kids.
const Acalculate = exports.calculate;
function calculate(gen, attacker, defender, move, field) {
    return (Acalculate || A.calculate)(typeof gen === 'number' ? data_1.Generations.get(gen) : gen, attacker, defender, move, field);
}
class Move extends A.Move {
    constructor(gen, name, options = {}) {
        super(typeof gen === 'number' ? data_1.Generations.get(gen) : gen, name, options);
    }
}
exports.Move = Move;
class Pokemon extends A.Pokemon {
    constructor(gen, name, options = {}) {
        super(typeof gen === 'number' ? data_1.Generations.get(gen) : gen, name, options);
    }
    static getForme(gen, speciesName, item, moveName) {
        return A.Pokemon.getForme(typeof gen === 'number' ? data_1.Generations.get(gen) : gen, speciesName, item, moveName);
    }
}
exports.Pokemon = Pokemon;
function calcStat(gen, stat, base, iv, ev, level, nature) {
    return A.Stats.calcStat(typeof gen === 'number' ? data_1.Generations.get(gen) : gen, stat === 'spc' ? 'spa' : stat, base, iv, ev, level, nature);
}
var field_1 = require("./field");
Object.defineProperty(exports, "Field", { enumerable: true, get: function () { return field_1.Field; } });
Object.defineProperty(exports, "Side", { enumerable: true, get: function () { return field_1.Side; } });
var result_1 = require("./result");
Object.defineProperty(exports, "Result", { enumerable: true, get: function () { return result_1.Result; } });
var index_1 = require("./data/index");
Object.defineProperty(exports, "Generations", { enumerable: true, get: function () { return index_1.Generations; } });
var util_1 = require("./util");
Object.defineProperty(exports, "toID", { enumerable: true, get: function () { return util_1.toID; } });
var abilities_1 = require("./data/abilities");
Object.defineProperty(exports, "ABILITIES", { enumerable: true, get: function () { return abilities_1.ABILITIES; } });
var items_1 = require("./data/items");
Object.defineProperty(exports, "ITEMS", { enumerable: true, get: function () { return items_1.ITEMS; } });
Object.defineProperty(exports, "MEGA_STONES", { enumerable: true, get: function () { return items_1.MEGA_STONES; } });
var moves_1 = require("./data/moves");
Object.defineProperty(exports, "MOVES", { enumerable: true, get: function () { return moves_1.MOVES; } });
var species_1 = require("./data/species");
Object.defineProperty(exports, "SPECIES", { enumerable: true, get: function () { return species_1.SPECIES; } });
var natures_1 = require("./data/natures");
Object.defineProperty(exports, "NATURES", { enumerable: true, get: function () { return natures_1.NATURES; } });
var types_1 = require("./data/types");
Object.defineProperty(exports, "TYPE_CHART", { enumerable: true, get: function () { return types_1.TYPE_CHART; } });
var stats_1 = require("./stats");
Object.defineProperty(exports, "STATS", { enumerable: true, get: function () { return stats_1.STATS; } });
Object.defineProperty(exports, "Stats", { enumerable: true, get: function () { return stats_1.Stats; } });
