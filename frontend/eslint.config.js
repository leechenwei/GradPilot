import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(js.configs.recommended, ...tseslint.configs.recommended, {
  languageOptions: { globals: { window: "readonly", document: "readonly", localStorage: "readonly", fetch: "readonly", crypto: "readonly", console: "readonly", TextDecoder: "readonly" } },
});
