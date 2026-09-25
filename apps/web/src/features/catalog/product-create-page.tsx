"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Controller,
  useFieldArray,
  useForm,
  useWatch,
  type DeepPartialSkipArrayKey,
} from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Bot, Plus, Trash2 } from "lucide-react";
import { centsToString, formatMoney, toCents } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label, Switch } from "@/components/ui/controls";
import { Card, CardHeader } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  FormActions,
  FormField,
  FormSection,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import { InlineError } from "@/components/app/states";
import { PropertyList } from "@/components/app/record";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError, errorMessage } from "@/services/api-client";
import type { ProductInput } from "@/features/business/types";
import { catalogService } from "./service";
import { CATALOG_CHANGED, useCategories, useDefaultCurrency } from "./hooks";
import { CURRENCY_PATTERN, PRICE_PATTERN, SKU_PATTERN } from "./lib";
import { CategoryDialog } from "./category-dialog";

const variantSchema = z.object({
  sku: z
    .string()
    .trim()
    .min(1, "Enter a SKU")
    .regex(
      SKU_PATTERN,
      "Letters, numbers, dots, dashes or underscores; start with a letter or number",
    ),
  name: z
    .string()
    .trim()
    .min(1, "Enter a variant name")
    .max(200, "Keep the name under 200 characters"),
  price: z.string().trim().regex(PRICE_PATTERN, "Enter a price like 12.50"),
  currency: z
    .string()
    .trim()
    .toUpperCase()
    .regex(CURRENCY_PATTERN, "3-letter code"),
  track_inventory: z.boolean(),
  low_stock_threshold: z
    .string()
    .trim()
    .regex(/^\d{0,7}$/, "Whole number or empty"),
});

const schema = z.object({
  offering_type: z.enum(["service", "product", "hybrid", "package"]),
  name: z
    .string()
    .trim()
    .min(1, "Enter a product name")
    .max(200, "Keep the name under 200 characters"),
  description: z
    .string()
    .trim()
    .max(5000, "Keep the description under 5,000 characters"),
  category_id: z.string(),
  pi_visible: z.boolean(),
  variants: z
    .array(variantSchema)
    .min(1, "Add at least one variant")
    .max(50, "A product can have up to 50 variants")
    .superRefine((variants, ctx) => {
      const seen = new Map<string, number>();
      variants.forEach((v, i) => {
        const key = v.sku.trim().toLowerCase();
        if (!key) return;
        if (seen.has(key))
          ctx.addIssue({
            code: "custom",
            path: [i, "sku"],
            message: "SKU already used above",
          });
        else seen.set(key, i);
      });
    }),
});
type Values = z.infer<typeof schema>;

const blankVariant = (currency: string): Values["variants"][number] => ({
  sku: "",
  name: "",
  price: "",
  currency,
  track_inventory: false,
  low_stock_threshold: "",
});

export function ProductCreatePage() {
  return (
    <RequirePermission permission="catalog.write" area="product creation">
      <ProductCreateInner />
    </RequirePermission>
  );
}

function ProductCreateInner() {
  const router = useRouter();
  const categories = useCategories();
  const { currency: defaultCurrency, lowStockThreshold } = useDefaultCurrency();
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      offering_type: "service",
      name: "",
      description: "",
      category_id: "",
      pi_visible: true,
      variants: [blankVariant("")],
    },
  });
  const { register, control, handleSubmit, setValue, getValues, formState } =
    form;
  const { fields, append, remove } = useFieldArray({
    control,
    name: "variants",
  });

  // Fill the workspace currency into variants that don't have one yet.
  useEffect(() => {
    if (!defaultCurrency) return;
    getValues("variants").forEach((v, i) => {
      if (!v.currency)
        setValue(`variants.${i}.currency`, defaultCurrency, {
          shouldValidate: true,
        });
    });
  }, [defaultCurrency, getValues, setValue]);

  useUnsavedChangesWarning(formState.isDirty && !done);

  const mutation = useScopedMutation(
    (input: ProductInput) => catalogService.createProduct(input),
    {
      invalidate: CATALOG_CHANGED,
      success: (p) => `“${p.name}” added to the catalog`,
      error: "Couldn't create this product.",
      onSuccess: (p) => {
        setDone(true);
        router.push(`/catalog/products/${p.id}`);
      },
    },
  );

  const submit = handleSubmit((v) => {
    setServerError(null);
    mutation.mutate(
      {
        offering_type: v.offering_type,
        name: v.name.trim(),
        description: v.description.trim(),
        category_id: v.category_id || null,
        pi_visible: v.pi_visible,
        variants: v.variants.map((x) => ({
          sku: x.sku.trim(),
          name: x.name.trim(),
          price: x.price.trim(),
          currency: x.currency,
          track_inventory:
            v.offering_type === "service" ? false : x.track_inventory,
          low_stock_threshold:
            x.track_inventory && x.low_stock_threshold
              ? Number(x.low_stock_threshold)
              : null,
        })),
      },
      {
        onError: (e) => {
          const message = errorMessage(e, "Couldn't create this product.");
          setServerError(
            e instanceof ApiError && e.status === 409
              ? `${message}. Choose a different SKU.`
              : message,
          );
        },
      },
    );
  });

  const watched = useWatch({ control });
  const variantErrors = formState.errors.variants;
  const arrayError = variantErrors?.root?.message ?? variantErrors?.message;

  return (
    <PageShell>
      <PageHeader
        title="Add offering"
        description="Create a service, product or package with approved pricing for quotes and orders."
        eyebrow={
          <Link
            href="/catalog/products"
            className="hover:text-foreground hover:underline"
          >
            Products
          </Link>
        }
      />
      <form onSubmit={submit} noValidate>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 rounded-xl border border-border bg-surface px-4 py-6 shadow-sm sm:px-6">
            <FormSection
              title="Basic information"
              description="How the product appears in quotes, orders and PI conversations."
            >
              <FormField label="Offering type" htmlFor="offering-type" required>
                <NativeSelect id="offering-type" {...register("offering_type")}>
                  <option value="service">Service</option>
                  <option value="product">Product</option>
                  <option value="hybrid">Hybrid offering</option>
                  <option value="package">Package</option>
                </NativeSelect>
              </FormField>
              <FormField
                label="Offering name"
                htmlFor="product-name"
                required
                error={formState.errors.name}
              >
                <Input
                  id="product-name"
                  autoFocus
                  placeholder="Ergonomic office chair"
                  aria-invalid={Boolean(formState.errors.name)}
                  {...register("name")}
                />
              </FormField>
              <FormField
                label="Description"
                htmlFor="product-description"
                optional
                error={formState.errors.description}
                help="Materials, sizes, what's included. PI uses this to answer customer questions."
              >
                <Textarea
                  id="product-description"
                  rows={5}
                  {...register("description")}
                />
              </FormField>
            </FormSection>

            <FormSection
              title="Category"
              description="Groups products for browsing and reporting."
            >
              <FormField label="Category" htmlFor="product-category" optional>
                <div className="flex gap-2">
                  <Controller
                    control={control}
                    name="category_id"
                    render={({ field }) => (
                      <NativeSelect
                        id="product-category"
                        disabled={categories.isPending}
                        {...field}
                      >
                        <option value="">No category</option>
                        {categories.data?.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setCategoryOpen(true)}
                  >
                    <Plus /> New
                  </Button>
                </div>
              </FormField>
            </FormSection>

            <FormSection
              title="Visibility"
              description="Control whether PI can offer this product."
            >
              <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3.5">
                <div>
                  <Label
                    htmlFor="product-pi"
                    className="flex items-center gap-1.5"
                  >
                    <Bot className="size-4 text-pi" aria-hidden="true" />{" "}
                    Visible to PI
                  </Label>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    PI only recommends and quotes active products that are
                    visible here. Turn this off for internal items or products
                    that need a salesperson.
                  </p>
                </div>
                <Controller
                  control={control}
                  name="pi_visible"
                  render={({ field }) => (
                    <Switch
                      id="product-pi"
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  )}
                />
              </div>
            </FormSection>

            <FormSection
              title="Pricing options"
              description="Set the price for a session, project, monthly service or product option. Stock tracking is optional for physical items."
            >
              <ol className="space-y-3">
                {fields.map((field, index) => {
                  const errors = variantErrors?.[index];
                  const tracked =
                    watched.variants?.[index]?.track_inventory ?? true;
                  const id = (name: string) => `variant-${index}-${name}`;
                  return (
                    <li
                      key={field.id}
                      className="rounded-lg border border-border bg-surface-muted/40 p-3.5"
                    >
                      <div className="mb-3 flex items-center justify-between gap-2">
                        <p className="text-[13px] font-semibold">
                          Variant {index + 1}
                        </p>
                        {fields.length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            onClick={() => remove(index)}
                            aria-label={`Remove variant ${index + 1}`}
                          >
                            <Trash2 />
                          </Button>
                        )}
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1.4fr_1fr_88px]">
                        <FormField
                          label="SKU"
                          htmlFor={id("sku")}
                          required
                          error={errors?.sku}
                        >
                          <Input
                            id={id("sku")}
                            className="font-mono"
                            placeholder="WEB-STARTER"
                            aria-invalid={Boolean(errors?.sku)}
                            {...register(`variants.${index}.sku`)}
                          />
                        </FormField>
                        <FormField
                          label="Name"
                          htmlFor={id("name")}
                          required
                          error={errors?.name}
                        >
                          <Input
                            id={id("name")}
                            placeholder="Black"
                            aria-invalid={Boolean(errors?.name)}
                            {...register(`variants.${index}.name`)}
                          />
                        </FormField>
                        <FormField
                          label="Price"
                          htmlFor={id("price")}
                          required
                          error={errors?.price}
                        >
                          <Input
                            id={id("price")}
                            inputMode="decimal"
                            className="tabular"
                            placeholder="0.00"
                            aria-invalid={Boolean(errors?.price)}
                            {...register(`variants.${index}.price`)}
                          />
                        </FormField>
                        <FormField
                          label="Currency"
                          htmlFor={id("currency")}
                          required
                          error={errors?.currency}
                        >
                          <Input
                            id={id("currency")}
                            maxLength={3}
                            className="uppercase"
                            aria-invalid={Boolean(errors?.currency)}
                            {...register(`variants.${index}.currency`)}
                          />
                        </FormField>
                      </div>
                      <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-3">
                        <div className="flex h-9 items-center gap-2">
                          <Controller
                            control={control}
                            name={`variants.${index}.track_inventory`}
                            render={({ field: f }) => (
                              <Switch
                                id={id("track")}
                                checked={
                                  watched.offering_type !== "service" && f.value
                                }
                                disabled={watched.offering_type === "service"}
                                onCheckedChange={f.onChange}
                              />
                            )}
                          />
                          <Label
                            htmlFor={id("track")}
                            className="cursor-pointer"
                          >
                            Track inventory
                          </Label>
                        </div>
                        {tracked && (
                          <FormField
                            label="Low-stock threshold"
                            htmlFor={id("threshold")}
                            optional
                            error={errors?.low_stock_threshold}
                            help={
                              lowStockThreshold !== undefined
                                ? `Workspace default: ${lowStockThreshold}`
                                : undefined
                            }
                          >
                            <Input
                              id={id("threshold")}
                              inputMode="numeric"
                              className="tabular w-32"
                              aria-invalid={Boolean(
                                errors?.low_stock_threshold,
                              )}
                              {...register(
                                `variants.${index}.low_stock_threshold`,
                              )}
                            />
                          </FormField>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
              {arrayError && (
                <p role="alert" className="text-xs font-medium text-danger">
                  {arrayError}
                </p>
              )}
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={fields.length >= 50}
                onClick={() =>
                  append(
                    blankVariant(
                      getValues("variants.0.currency") || defaultCurrency || "",
                    ),
                  )
                }
              >
                <Plus /> Add variant
              </Button>
              {serverError && <InlineError message={serverError} />}
            </FormSection>
          </div>

          <aside className="xl:sticky xl:top-4 xl:self-start">
            <ReviewCard
              values={watched}
              categoryName={
                categories.data?.find((c) => c.id === watched.category_id)?.name
              }
            />
          </aside>
        </div>
        <FormActions
          dirty={formState.isDirty}
          disabled={!defaultCurrency}
          saving={mutation.isPending}
          submitLabel="Create offering"
          onCancel={() => router.push("/catalog/products")}
        />
      </form>
      <CategoryDialog
        open={categoryOpen}
        onOpenChange={setCategoryOpen}
        onCreated={(c) => setValue("category_id", c.id, { shouldDirty: true })}
      />
    </PageShell>
  );
}

type Watched = DeepPartialSkipArrayKey<Values>;

function ReviewCard({
  values,
  categoryName,
}: {
  values: Watched;
  categoryName?: string;
}) {
  const variants = useMemo(() => values.variants ?? [], [values.variants]);
  const summary = useMemo(() => {
    const valid = variants.filter(
      (v) => v?.price && PRICE_PATTERN.test(v.price.trim()),
    );
    const currencies = [
      ...new Set(
        variants.map((v) => v?.currency?.toUpperCase()).filter(Boolean),
      ),
    ] as string[];
    if (!valid.length) return { range: "—", currencies };
    const cents = valid.map((v) => toCents(v!.price!.trim()));
    const min = cents.reduce((a, b) => (a < b ? a : b));
    const max = cents.reduce((a, b) => (a > b ? a : b));
    const cur = currencies[0] ?? "USD";
    const range =
      min === max
        ? formatMoney(centsToString(min), cur)
        : `${formatMoney(centsToString(min), cur)} – ${formatMoney(centsToString(max), cur)}`;
    return { range, currencies };
  }, [variants]);
  const tracked = variants.filter((v) => v?.track_inventory).length;

  return (
    <Card>
      <CardHeader title="Review" description="What will be created" />
      <div className="px-4 pb-4">
        <p className="truncate text-[15px] font-semibold">
          {values.name?.trim() || (
            <span className="text-muted-foreground">Untitled product</span>
          )}
        </p>
        <PropertyList
          className="mt-2"
          items={[
            {
              label: "Category",
              value: categoryName ?? (
                <span className="text-muted-foreground">None</span>
              ),
            },
            {
              label: "PI",
              value: values.pi_visible ? (
                <span className="text-pi">Visible</span>
              ) : (
                "Hidden"
              ),
            },
            {
              label: "Variants",
              value: <span className="tabular">{variants.length}</span>,
            },
            {
              label: "Price",
              value: <span className="tabular">{summary.range}</span>,
            },
            {
              label: "Inventory",
              value: `${tracked} of ${variants.length} tracked`,
            },
          ]}
        />
        {summary.currencies.length > 1 && (
          <p className="mt-2 text-xs text-warning">
            Variants use more than one currency ({summary.currencies.join(", ")}
            ).
          </p>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          New offerings start active. Services can be quoted and ordered
          immediately without inventory.
        </p>
      </div>
    </Card>
  );
}
