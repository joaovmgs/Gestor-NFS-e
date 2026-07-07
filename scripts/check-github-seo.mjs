import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const readme = await readFile("README.md", "utf8");
const packageJson = JSON.parse(await readFile("package.json", "utf8"));

const normalizedReadme = normalize(readme);
const normalizedKeywords = (packageJson.keywords ?? []).map(normalize);
const normalizedDescription = normalize(packageJson.description ?? "");

assert.match(readme, /^# Gestor NFS-e/m, "README deve iniciar com o nome do app.");
assert.ok(
  normalizedDescription.includes("nfse") || normalizedDescription.includes("nfs-e"),
  "package.json precisa descrever NFS-e/NFSe."
);
assert.ok(
  packageJson.repository?.url?.includes("Gestor-NFS-e"),
  "package.json precisa apontar para o repositorio GitHub."
);

for (const keyword of [
  "nfse",
  "nfse-nacional",
  "danfse",
  "xml-nfse",
  "contador"
]) {
  assert.ok(
    normalizedKeywords.includes(keyword),
    `package.json precisa conter a keyword ${keyword}.`
  );
}

for (const term of [
  "nota fiscal de servico",
  "nfs-e nacional",
  "baixar",
  "xml",
  "pdf",
  "xlsx",
  "danfse",
  "certificado",
  "contador",
  "windows"
]) {
  assert.ok(
    normalizedReadme.includes(term),
    `README precisa conter o termo buscavel: ${term}.`
  );
}

assert.ok(
  normalizedReadme.includes("releases") && normalizedReadme.includes("gestor-nfse-setup"),
  "README precisa orientar o download do instalador nas releases."
);
assert.ok(
  normalizedReadme.includes("danfse v2.0") && normalizedReadme.includes("nota tecnica"),
  "README precisa documentar o padrao DANFSe usado."
);

function normalize(value) {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}
