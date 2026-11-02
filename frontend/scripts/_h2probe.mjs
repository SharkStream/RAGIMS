// Temporary H2 probe: verify the exact API calls the documents page makes.
const BASE = "http://127.0.0.1:8000/api";

async function j(path) {
  const resp = await fetch(BASE + path);
  const body = await resp.json();
  if (body.code !== "OK") throw new Error(`${path}: ${body.code} ${body.message}`);
  return body.data;
}

const list = await j("/documents?page=1&page_size=5");
console.log(`[1] GET /documents -> code OK, total=${list.total}, page=${list.page}`);
if (list.items.length) {
  const doc = list.items[0];
  console.log(`    first doc: type=${doc.file_type} status=${doc.status} v${doc.current_version}`);
  const detail = await j(`/documents/${doc.id}`);
  console.log(`[2] GET /documents/{id} -> latest_version=${detail.latest_version ? "v" + detail.latest_version.version + " parse=" + detail.latest_version.parse_status : "null"}`);
  const chunks = await j(`/documents/${doc.id}/chunks?page=1&page_size=10`);
  console.log(`[3] GET /documents/{id}/chunks -> total=${chunks.total}, fields=${chunks.items[0] ? Object.keys(chunks.items[0]).join("/") : "empty"}`);
  const filtered = await j(`/documents?page=1&page_size=5&file_type=${doc.file_type}&keyword=${encodeURIComponent(doc.title.slice(0, 4))}`);
  console.log(`[4] filters (file_type + keyword) -> total=${filtered.total}`);
} else {
  console.log("    (no documents yet — upload one via the page to exercise the rest)");
}
console.log("H2 API probe: OK");
