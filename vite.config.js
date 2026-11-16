import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
	plugins: [svelte()],
	// Relative base so the site works both at a domain root and under a
	// GitHub Pages project path (https://<user>.github.io/<repo>/).
	base: './',
	// The ETL writes the frontend data to static/data/, so serve and copy that
	// directory (Vite's default would be public/).
	publicDir: 'static',
	build: {
		outDir: 'build'
	}
});
