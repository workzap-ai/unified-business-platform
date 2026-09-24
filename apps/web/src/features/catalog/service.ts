import { z } from "zod";
import {
  apiRequest,
  ApiError,
  pageSchema,
  type Page,
} from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { toCents, centsToString } from "@/lib/format";
import {
  categorySchema,
  productDetailSchema,
  productListItemSchema,
  variantSchema,
  type Category,
  type ListParams,
  type ProductDetail,
  type ProductInput,
  type ProductListItem,
  type Variant,
  type VariantInput,
} from "@/features/business/types";

export interface CatalogService {
  categories(): Promise<Category[]>;
  createCategory(input: {
    name: string;
    slug: string;
    description: string;
  }): Promise<Category>;
  products(
    params: ListParams & { categoryId?: string },
  ): Promise<Page<ProductListItem>>;
  product(id: string): Promise<ProductDetail>;
  createProduct(input: ProductInput): Promise<ProductDetail>;
  updateProduct(
    id: string,
    input: Partial<
      Pick<
        ProductDetail,
        "name" | "description" | "category_id" | "status" | "pi_visible"
      >
    >,
  ): Promise<ProductDetail>;
  addVariant(productId: string, input: VariantInput): Promise<Variant>;
  updateVariant(
    id: string,
    input: Partial<VariantInput & { status: Variant["status"] }>,
  ): Promise<Variant>;
}

const live: CatalogService = {
  categories: () =>
    apiRequest("GET", "/catalog/categories", z.array(categorySchema)),
  createCategory: (input) =>
    apiRequest("POST", "/catalog/categories", categorySchema, { body: input }),
  products: ({ page = 1, pageSize = 25, search, status, categoryId }) =>
    apiRequest("GET", "/catalog/products", pageSchema(productListItemSchema), {
      query: {
        page,
        page_size: pageSize,
        search,
        status,
        category_id: categoryId,
      },
    }),
  product: (id) =>
    apiRequest("GET", `/catalog/products/${id}`, productDetailSchema),
  createProduct: (input) =>
    apiRequest("POST", "/catalog/products", productDetailSchema, {
      body: input,
    }),
  updateProduct: (id, input) =>
    apiRequest("PATCH", `/catalog/products/${id}`, productDetailSchema, {
      body: input,
    }),
  addVariant: (productId, input) =>
    apiRequest(
      "POST",
      `/catalog/products/${productId}/variants`,
      variantSchema,
      { body: input },
    ),
  updateVariant: (id, input) =>
    apiRequest("PATCH", `/catalog/variants/${id}`, variantSchema, {
      body: input,
    }),
};

function toListItem(p: ProductDetail): ProductListItem {
  const prices = p.variants.map((v) => toCents(v.price));
  const min = prices.length ? prices.reduce((a, b) => (a < b ? a : b)) : null;
  const max = prices.length ? prices.reduce((a, b) => (a > b ? a : b)) : null;
  const { variants, ...rest } = p;
  return {
    ...rest,
    variant_count: variants.length,
    min_price: min === null ? null : centsToString(min),
    max_price: max === null ? null : centsToString(max),
    currency: variants[0]?.currency ?? null,
  };
}

function findProduct(id: string) {
  const product = demoBusiness().products.find((p) => p.id === id);
  if (!product) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return product;
}

function assertSku(sku: string) {
  const exists = demoBusiness().products.some((p) =>
    p.variants.some((v) => v.sku.toLowerCase() === sku.toLowerCase()),
  );
  if (exists)
    throw new ApiError(
      409,
      "RESOURCE_CONFLICT",
      undefined,
      "A variant with this SKU already exists",
    );
}

const demo: CatalogService = {
  async categories() {
    await demoDelay(100);
    return [...demoBusiness().categories];
  },
  async createCategory(input) {
    await demoDelay(250);
    if (demoBusiness().categories.some((c) => c.slug === input.slug))
      throw new ApiError(
        409,
        "RESOURCE_CONFLICT",
        undefined,
        "A category with this slug already exists",
      );
    const category = { id: demoId("cat"), ...input };
    demoBusiness().categories.push(category);
    return category;
  },
  async products({ page = 1, pageSize = 25, search, status, categoryId }) {
    await demoDelay();
    const rows = demoBusiness()
      .products.filter(
        (p) =>
          (!status || p.status === status) &&
          (!categoryId || p.category_id === categoryId) &&
          (!search ||
            matches(p.name, search) ||
            p.variants.some((v) => matches(v.sku, search))),
      )
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(toListItem);
    return paginate(rows, page, pageSize);
  },
  async product(id) {
    await demoDelay();
    const p = findProduct(id);
    return { ...p, variants: p.variants.map((v) => ({ ...v })) };
  },
  async createProduct(input) {
    await demoDelay(400);
    const skus = input.variants.map((v) => v.sku.toLowerCase());
    if (new Set(skus).size !== skus.length)
      throw new ApiError(
        422,
        "DUPLICATE_SKU",
        undefined,
        "Each variant needs a unique SKU",
      );
    input.variants.forEach((v) => assertSku(v.sku));
    const business = demoBusiness();
    const id = demoId("prd");
    const category = business.categories.find(
      (c) => c.id === input.category_id,
    );
    const product: ProductDetail = {
      id,
      name: input.name,
      description: input.description,
      category_id: input.category_id,
      category_name: category?.name ?? null,
      status: "active",
      pi_visible: input.pi_visible,
      attributes: {},
      created_at: new Date().toISOString(),
      variants: input.variants.map((v) => ({
        id: demoId("var"),
        product_id: id,
        status: "active",
        attributes: {},
        ...v,
      })),
    };
    business.products.unshift(product);
    return product;
  },
  async updateProduct(id, input) {
    await demoDelay(250);
    const product = findProduct(id);
    Object.assign(product, input);
    if (input.category_id !== undefined)
      product.category_name =
        demoBusiness().categories.find((c) => c.id === input.category_id)
          ?.name ?? null;
    return demo.product(id);
  },
  async addVariant(productId, input) {
    await demoDelay(300);
    const product = findProduct(productId);
    assertSku(input.sku);
    const variant: Variant = {
      id: demoId("var"),
      product_id: productId,
      status: "active",
      attributes: {},
      ...input,
    };
    product.variants.push(variant);
    return variant;
  },
  async updateVariant(id, input) {
    await demoDelay(250);
    for (const product of demoBusiness().products) {
      const variant = product.variants.find((v) => v.id === id);
      if (variant) {
        Object.assign(variant, input);
        return { ...variant };
      }
    }
    throw new ApiError(404, "RESOURCE_NOT_FOUND");
  },
};

export const catalogService = select<CatalogService>({ demo, live });
