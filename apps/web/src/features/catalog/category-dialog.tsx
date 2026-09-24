"use client";

import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
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
import { ApiError, errorMessage } from "@/services/api-client";
import type { Category } from "@/features/business/types";
import { catalogService } from "./service";
import { SLUG_PATTERN, slugify } from "./lib";

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter a name")
    .max(120, "Keep the name under 120 characters"),
  slug: z
    .string()
    .trim()
    .min(1, "Enter a slug")
    .max(80, "Keep the slug under 80 characters")
    .regex(
      SLUG_PATTERN,
      "Use lowercase letters, numbers and single hyphens, e.g. office-chairs",
    ),
  description: z
    .string()
    .trim()
    .max(500, "Keep the description under 500 characters"),
});
type Values = z.infer<typeof schema>;

export function CategoryDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (category: Category) => void;
}) {
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    setError,
    control,
    formState,
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", slug: "", description: "" },
  });
  useEffect(() => {
    if (open) {
      reset({ name: "", slug: "", description: "" });
    }
  }, [open, reset]);
  const name = useWatch({ control, name: "name" });
  // Keep generating from the name until the member edits the slug by hand.
  const slugTouched = Boolean(formState.dirtyFields.slug);
  useEffect(() => {
    if (!slugTouched) setValue("slug", slugify(name));
  }, [name, slugTouched, setValue]);

  const mutation = useScopedMutation(
    (input: Values) => catalogService.createCategory(input),
    {
      invalidate: [["catalog", "categories"]],
      success: (c) => `Category “${c.name}” created`,
      error: "Couldn't create this category.",
      onSuccess: (category) => {
        onCreated?.(category);
        onOpenChange(false);
      },
    },
  );

  const submit = handleSubmit((values) =>
    mutation.mutate(
      {
        name: values.name.trim(),
        slug: values.slug.trim(),
        description: values.description.trim(),
      },
      {
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409)
            setError("slug", {
              message: "Another category already uses this slug",
            });
        },
      },
    ),
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}
    >
      <DialogContent size="sm">
        <DialogHeader
          title="New category"
          description="Group related products so customers and PI can browse them."
        />
        <form
          onSubmit={(e) => {
            // Stop the submit from reaching a parent form (this dialog is also used inside the product form).
            e.stopPropagation();
            void submit(e);
          }}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogBody className="space-y-4">
            <FormField
              label="Name"
              htmlFor="category-name"
              required
              error={formState.errors.name}
            >
              <Input
                id="category-name"
                autoFocus
                placeholder="Office chairs"
                aria-invalid={Boolean(formState.errors.name)}
                {...register("name")}
              />
            </FormField>
            <FormField
              label="Slug"
              htmlFor="category-slug"
              required
              error={formState.errors.slug}
              help="Used in links and integrations. Generated from the name."
            >
              <Input
                id="category-slug"
                className="font-mono"
                aria-invalid={Boolean(formState.errors.slug)}
                {...register("slug")}
              />
            </FormField>
            <FormField
              label="Description"
              htmlFor="category-description"
              optional
              error={formState.errors.description}
            >
              <Textarea
                id="category-description"
                rows={3}
                {...register("description")}
              />
            </FormField>
            {mutation.isError &&
              !(
                mutation.error instanceof ApiError &&
                mutation.error.status === 409
              ) && <InlineError message={errorMessage(mutation.error)} />}
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
              Create category
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
