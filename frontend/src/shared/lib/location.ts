export function currentSource(): "demo" | "real" {
  return new URLSearchParams(location.search).get("source") === "real"
    ? "real"
    : "demo";
}

export function replaceFilter(key: "source" | "tab", value: string) {
  const url = new URL(location.href);
  url.searchParams.set(key, value);
  if (key === "source") {
    for (const id of ["sku", "pedido", "lancamento"])
      url.searchParams.delete(id);
  }
  window.history.replaceState(window.history.state, "", url);
}
