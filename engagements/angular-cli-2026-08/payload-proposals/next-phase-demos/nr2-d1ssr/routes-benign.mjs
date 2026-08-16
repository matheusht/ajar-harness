const routes = [
  { path: "dashboard", loadChildren: () => import("./admin/admin.module").then((m) => m.AdminModule) }
];
var stdin_default = routes;
export {
  stdin_default as default
};
