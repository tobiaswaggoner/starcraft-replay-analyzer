import { defineStore } from "pinia";
import { api, type TrainingTarget, type TrainingTargetInput } from "../api/client";

interface State {
  items: TrainingTarget[];
  loading: boolean;
}

export const useTargetsStore = defineStore("targets", {
  state: (): State => ({ items: [], loading: false }),
  actions: {
    async load() {
      this.loading = true;
      try {
        const r = await api.listTargets();
        this.items = r.items;
      } finally {
        this.loading = false;
      }
    },
    async create(t: TrainingTargetInput) {
      await api.createTarget(t);
      await this.load();
    },
    async update(id: number, t: TrainingTargetInput) {
      await api.updateTarget(id, t);
      await this.load();
    },
    async remove(id: number) {
      await api.deleteTarget(id);
      await this.load();
    },
    async toggleEnabled(t: TrainingTarget) {
      await api.updateTarget(t.id, { ...t, enabled: !t.enabled });
      await this.load();
    },
  },
});
