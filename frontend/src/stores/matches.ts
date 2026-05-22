import { defineStore } from "pinia";
import { api, type Match, type Facets } from "../api/client";

interface State {
  items: Match[];
  total: number;
  loading: boolean;
  facets: Facets;
  filters: {
    matchup?: string; race?: string; result?: string; map_name?: string;
    mode?: string; tag?: string; game_format?: string;
  };
}

export const useMatchesStore = defineStore("matches", {
  state: (): State => ({
    items: [],
    total: 0,
    loading: false,
    facets: { maps: [], matchups: [], game_formats: [], races: [], results: [], modes: [], tags: [] },
    filters: {},
  }),
  actions: {
    async loadFacets() {
      this.facets = await api.facets();
    },
    async load() {
      this.loading = true;
      try {
        const res = await api.listMatches(this.filters);
        this.items = res.items;
        this.total = res.total;
      } finally {
        this.loading = false;
      }
    },
    async setFilter<K extends keyof State["filters"]>(key: K, value: State["filters"][K]) {
      if (value === "") (this.filters as any)[key] = undefined;
      else this.filters[key] = value;
      await this.load();
    },
    async scan() {
      await api.scan();
      await this.load();
    },
  },
});
