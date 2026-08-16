const routes = [
  { path: "x" },
  { path: "y", loadChildren: (() => {
    globalThis.__pwned = "D1-SSR-RUNTIME-MARKER";
    return () => import("./y/y.module");
  })() },
  { path: "", loadChildren: () => import("./admin/admin.module").then((m) => m.AdminModule) }
];
var stdin_default = routes;
export {
  stdin_default as default
};
