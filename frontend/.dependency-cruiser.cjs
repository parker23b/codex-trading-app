module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment:
        "Circular dependencies make the frontend harder to reason about.",
      from: {},
      to: {
        circular: true,
      },
    },
    {
      name: "no-components-importing-app",
      severity: "error",
      comment: "Reusable components should not import Next app routes/pages.",
      from: {
        path: "^components",
      },
      to: {
        path: "^app",
      },
    },
    {
      name: "no-lib-importing-components",
      severity: "warn",
      comment: "Shared lib code should stay UI-agnostic.",
      from: {
        path: "^lib",
      },
      to: {
        path: "^components",
      },
    },
  ],
  options: {
    tsPreCompilationDeps: true,
    doNotFollow: {
      path: "node_modules",
    },
    exclude: {
      path: "node_modules|\\.next",
    },
  },
};
