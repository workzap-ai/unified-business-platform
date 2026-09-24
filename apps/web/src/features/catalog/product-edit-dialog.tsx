"use client";

import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { InlineError } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import type { ProductDetail } from "@/features/business/types";
import { catalogService } from "./service";
import { CATALOG_CHANGED, useCategories } from "./hooks";
import { CategoryDialog } from "./category-dialog";

const schema = z.object({
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
});
type Values = z.infer<typeof schema>;

export function ProductEditDialog({
  product,
  open,
  onOpenChange,
}: {
  product: ProductDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const categories = useCategories(open);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const { register, handleSubmit, reset, setValue, control, formState } =
    useForm<Values>({
      resolver: zodResolver(schema),
      defaultValues: {
        name: product.name,
        description: product.description,
        category_id: product.category_id ?? "",
      },
    });
  useEffect(() => {
    if (open)
      reset({
        name: product.name,
        description: product.description,
        category_id: product.category_id ?? "",
      });
  }, [open, product, reset]);

  const mutation = useScopedMutation(
    (input: {
      name: string;
      description: string;
      category_id: string | null;
    }) => catalogService.updateProduct(product.id, input),
    {
      invalidate: CATALOG_CHANGED,
      success: "Product updated",
      error: "Couldn't save this product.",
      onSuccess: () => onOpenChange(false),
    },
  );

  const submit = handleSubmit((v) =>
    mutation.mutate({
      name: v.name.trim(),
      description: v.description.trim(),
      category_id: v.category_id || null,
    }),
  );

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}
      >
        <DialogContent size="md">
          <DialogHeader
            title="Edit product"
            description="Variants, prices and stock are managed on their own tabs."
          />
          <form
            onSubmit={submit}
            noValidate
            className="flex min-h-0 flex-1 flex-col"
          >
            <DialogBody className="space-y-4">
              <FormField
                label="Name"
                htmlFor="edit-product-name"
                required
                error={formState.errors.name}
              >
                <Input
                  id="edit-product-name"
                  aria-invalid={Boolean(formState.errors.name)}
                  {...register("name")}
                />
              </FormField>
              <FormField
                label="Description"
                htmlFor="edit-product-description"
                optional
                error={formState.errors.description}
                help="PI uses this to describe the product to customers."
              >
                <Textarea
                  id="edit-product-description"
                  rows={5}
                  {...register("description")}
                />
              </FormField>
              <FormField
                label="Category"
                htmlFor="edit-product-category"
                optional
              >
                <div className="flex gap-2">
                  <Controller
                    control={control}
                    name="category_id"
                    render={({ field }) => (
                      <NativeSelect
                        id="edit-product-category"
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
                    size="icon"
                    aria-label="New category"
                    onClick={() => setCategoryOpen(true)}
                  >
                    <Plus />
                  </Button>
                </div>
              </FormField>
              {mutation.isError && (
                <InlineError message={errorMessage(mutation.error)} />
              )}
            </DialogBody>
            <DialogFooter>
              <Button
                type="button"
                variant="secondary"
                onClick={() => onOpenChange(false)}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" loading={mutation.isPending}>
                Save changes
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <CategoryDialog
        open={categoryOpen}
        onOpenChange={setCategoryOpen}
        onCreated={(c) => setValue("category_id", c.id, { shouldDirty: true })}
      />
    </>
  );
}
