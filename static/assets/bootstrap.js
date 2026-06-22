const appVersion = "3.12.0";

async function loadFragment(mountNode) {
  const fragmentUrl = mountNode.dataset.fragment;
  if (!fragmentUrl) {
    return;
  }

  const response = await fetch(`${fragmentUrl}?v=${appVersion}`);
  if (!response.ok) {
    throw new Error(`加载页面片段失败：${fragmentUrl}`);
  }
  mountNode.outerHTML = await response.text();
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.defer = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`加载脚本失败：${src}`));
    document.body.appendChild(script);
  });
}

async function bootstrapConsole() {
  const fragmentMounts = Array.from(document.querySelectorAll("[data-fragment]"));
  await Promise.all(fragmentMounts.map(loadFragment));
  await loadScript(`/static/assets/app.js?v=${appVersion}`);
}

bootstrapConsole().catch((error) => {
  document.body.innerHTML = `<main class="bootstrap-error">
    <h1>控制台加载失败</h1>
    <p>${error.message}</p>
  </main>`;
});
