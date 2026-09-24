import { z } from "zod";
import { apiRequest, ApiError, pageSchema, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness, variantIndex } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import {
  locationSchema,
  movementSchema,
  stockLevelSchema,
  type AdjustmentInput,
  type Location,
  type Movement,
  type StockLevel,
} from "@/features/business/types";

export interface InventoryService {
  locations(): Promise<Location[]>;
  createLocation(input: { name: string; code: string; branch_id: string | null }): Promise<Location>;
  levels(params: { page?: number; pageSize?: number; search?: string; locationId?: string; lowOnly?: boolean }): Promise<Page<StockLevel>>;
  movements(params: { page?: number; pageSize?: number; variantId?: string }): Promise<Page<Movement>>;
  adjust(input: AdjustmentInput): Promise<Movement>;
}

const live: InventoryService = {
  locations: () => apiRequest("GET", "/inventory/locations", z.array(locationSchema)),
  createLocation: (input) => apiRequest("POST", "/inventory/locations", locationSchema, { body: input }),
  levels: ({ page = 1, pageSize = 25, search, locationId, lowOnly }) =>
    apiRequest("GET", "/inventory/levels", pageSchema(stockLevelSchema), {
      query: { page, page_size: pageSize, search, location_id: locationId, low_only: lowOnly || undefined },
    }),
  movements: ({ page = 1, pageSize = 25, variantId }) =>
    apiRequest("GET", "/inventory/movements", pageSchema(movementSchema), {
      query: { page, page_size: pageSize, variant_id: variantId },
    }),
  adjust: (input) => apiRequest("POST", "/inventory/adjustments", movementSchema, { body: input }),
};

function levelRows(): StockLevel[] {
  const business = demoBusiness();
  const index = variantIndex(business);
  const threshold = business.settings.low_stock_threshold;
  return business.stock.flatMap((row) => {
    const entry = index.get(row.variant_id);
    const location = business.locations.find((l) => l.id === row.location_id);
    if (!entry || !location) return [];
    const limit = entry.variant.low_stock_threshold ?? threshold;
    const available = row.on_hand - row.reserved;
    return [{
      variant_id: row.variant_id,
      product_id: entry.product.id,
      product_name: entry.product.name,
      variant_name: entry.variant.name,
      sku: entry.variant.sku,
      location_id: location.id,
      location_name: location.name,
      on_hand: row.on_hand,
      reserved: row.reserved,
      available,
      low_stock_threshold: limit,
      is_low: available <= limit,
    }];
  });
}

const demo: InventoryService = {
  async locations() {
    await demoDelay(100);
    return [...demoBusiness().locations];
  },
  async createLocation(input) {
    await demoDelay(250);
    if (demoBusiness().locations.some((l) => l.code === input.code))
      throw new ApiError(409, "RESOURCE_CONFLICT", undefined, "A location with this code already exists");
    const location: Location = { id: demoId("loc"), is_default: demoBusiness().locations.length === 0, status: "active", ...input };
    demoBusiness().locations.push(location);
    return location;
  },
  async levels({ page = 1, pageSize = 25, search, locationId, lowOnly }) {
    await demoDelay();
    const rows = levelRows()
      .filter((l) => (!locationId || l.location_id === locationId) && (!lowOnly || l.is_low) && (!search || matches(l.product_name, search) || matches(l.sku, search)))
      .sort((a, b) => a.product_name.localeCompare(b.product_name) || a.sku.localeCompare(b.sku));
    return paginate(rows, page, pageSize);
  },
  async movements({ page = 1, pageSize = 25, variantId }) {
    await demoDelay();
    const rows = demoBusiness().movements.filter((m) => !variantId || m.variant_id === variantId).sort((a, b) => b.created_at.localeCompare(a.created_at));
    return paginate(rows, page, pageSize);
  },
  async adjust(input) {
    await demoDelay(300);
    const business = demoBusiness();
    if (input.quantity === 0) throw new ApiError(422, "INVALID_QUANTITY", undefined, "Quantity must not be zero");
    if (input.kind !== "adjustment" && input.quantity < 0)
      throw new ApiError(422, "INVALID_QUANTITY", undefined, "Receipts and returns add stock");
    const location = business.locations.find((l) => l.id === input.location_id) ?? business.locations.find((l) => l.is_default);
    if (!location) throw new ApiError(422, "NO_LOCATION", undefined, "Create a location first");
    let row = business.stock.find((s) => s.variant_id === input.variant_id && s.location_id === location.id);
    if (!row) {
      row = { variant_id: input.variant_id, location_id: location.id, on_hand: 0, reserved: 0 };
      business.stock.push(row);
    }
    const balance = row.on_hand + input.quantity;
    if (balance < row.reserved || balance < 0)
      throw new ApiError(422, "INSUFFICIENT_STOCK", undefined, "Not enough stock available");
    row.on_hand = balance;
    const movement: Movement = {
      id: demoId("mov"), variant_id: input.variant_id, location_id: location.id, quantity: input.quantity, kind: input.kind,
      reason: input.reason, balance_after: balance, ref_type: "manual", ref_id: null, actor_label: "Amina Rahman", created_at: new Date().toISOString(),
    };
    business.movements.unshift(movement);
    return movement;
  },
};

export const inventoryService = select<InventoryService>({ demo, live });
export { levelRows as demoLevelRows };
