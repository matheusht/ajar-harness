function factory() {
  return function assignLater() {
    exports.notTopLevel = true;
  };
}

void factory;
