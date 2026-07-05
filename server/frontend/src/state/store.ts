import { create } from 'zustand';

/**
 * Global application state for PRIIS. The store tracks the currently
 * selected entity (e.g., a contract, site, or anomaly) and exposes
 * a function to update this selection. Additional state fields
 * (such as active module, filters, timeline cursor) should be
 * added as the application grows.
 */
interface AppState {
  selected: any | null;
  setSelection: (entity: any) => void;
  // Per-layer on/off state keyed by catalog layer_id. Populated by the Layer
  // Catalog pane; consumed by MapPane once geometry/pins are wired in a later pass.
  layerVisibility: Record<string, boolean>;
  setLayerVisible: (layerId: string, visible: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selected: null,
  setSelection: (entity) => set({ selected: entity }),
  layerVisibility: {},
  setLayerVisible: (layerId, visible) =>
    set((s) => ({ layerVisibility: { ...s.layerVisibility, [layerId]: visible } })),
}));