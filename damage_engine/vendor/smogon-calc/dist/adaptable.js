"use strict";
// By default, importing `@smogon/calc` provides a convenience wrapper that is roughly equivalent
// to importing `@smogon/calc/adaptable` and `import Generations from '@smogon/calc/data'` and
// using  `Generations` to populate the `Generation` param to these exports. Alternatively, an
// application may implement a different `@smogon/calc/data/interface` and pass a `Generation` from
// that to these exports.
Object.defineProperty(exports, "__esModule", { value: true });
exports.Stats = exports.Result = exports.Side = exports.Field = exports.Move = exports.Pokemon = exports.calculate = void 0;
var calc_1 = require("./calc");
Object.defineProperty(exports, "calculate", { enumerable: true, get: function () { return calc_1.calculate; } });
var pokemon_1 = require("./pokemon");
Object.defineProperty(exports, "Pokemon", { enumerable: true, get: function () { return pokemon_1.Pokemon; } });
var move_1 = require("./move");
Object.defineProperty(exports, "Move", { enumerable: true, get: function () { return move_1.Move; } });
var field_1 = require("./field");
Object.defineProperty(exports, "Field", { enumerable: true, get: function () { return field_1.Field; } });
Object.defineProperty(exports, "Side", { enumerable: true, get: function () { return field_1.Side; } });
var result_1 = require("./result");
Object.defineProperty(exports, "Result", { enumerable: true, get: function () { return result_1.Result; } });
var stats_1 = require("./stats");
Object.defineProperty(exports, "Stats", { enumerable: true, get: function () { return stats_1.Stats; } });
