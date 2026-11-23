/**
 * Previous/next extent stack for map navigation. `push` records a settled
 * view (call it from `moveend`); `back`/`forward` return the view to jump to
 * and arm a one-shot guard so the resulting `moveend` is not recorded again.
 */
export interface Extent {
  center: [number, number];
  zoom: number;
}

function same(a: Extent, b: Extent): boolean {
  return (
    Math.abs(a.zoom - b.zoom) < 0.01 &&
    Math.abs(a.center[0] - b.center[0]) < 1e-6 &&
    Math.abs(a.center[1] - b.center[1]) < 1e-6
  );
}

export class ExtentHistory {
  private stack: Extent[] = [];
  private index = -1;
  private suppressNext = false;

  constructor(private readonly limit = 50) {}

  push(extent: Extent): void {
    if (this.suppressNext) {
      this.suppressNext = false;
      return;
    }
    const current = this.stack[this.index];
    if (current && same(current, extent)) return;
    this.stack = [...this.stack.slice(0, this.index + 1), extent].slice(-this.limit);
    this.index = this.stack.length - 1;
  }

  back(): Extent | null {
    if (!this.canBack) return null;
    this.index -= 1;
    this.suppressNext = true;
    return this.stack[this.index];
  }

  forward(): Extent | null {
    if (!this.canForward) return null;
    this.index += 1;
    this.suppressNext = true;
    return this.stack[this.index];
  }

  get canBack(): boolean {
    return this.index > 0;
  }

  get canForward(): boolean {
    return this.index >= 0 && this.index < this.stack.length - 1;
  }
}
