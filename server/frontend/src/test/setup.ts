import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Testing Library only auto-registers cleanup when vitest globals are on. This
// harness imports describe/it/expect explicitly (see vitest.config.ts), so the
// unmount has to be wired up here or mounted trees leak between test files.
afterEach(cleanup);
