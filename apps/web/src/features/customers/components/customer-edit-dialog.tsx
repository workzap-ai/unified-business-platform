"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation } from "@/hooks/use-scoped";
import type { Customer } from "@/features/business/types";
import { customersService } from "../service";
import {
  applyCustomerServerError,
  customerFormSchema,
  CustomerFormStack,
  customerToForm,
  formToInput,
  type CustomerFormValues,
} from "./customer-form";

export function CustomerEditDialog({
  customer,
  open,
  onOpenChange,
}: {
  customer: Customer;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<CustomerFormValues>({
    resolver: zodResolver(customerFormSchema),
    defaultValues: customerToForm(customer),
  });

  useEffect(() => {
    if (open) form.reset(customerToForm(customer));
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const update = useScopedMutation(
    (values: CustomerFormValues) =>
      customersService.update(customer.id, formToInput(values)),
    {
      invalidate: [["customers"]],
      success: "Customer updated",
      error: "Changes couldn't be saved. Please try again.",
    },
  );

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await update.mutateAsync(values);
      onOpenChange(false);
    } catch (error) {
      applyCustomerServerError(form, error);
    }
  });

  const saving = update.isPending;
  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="md">
        <form
          onSubmit={onSubmit}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogHeader
            title="Edit customer"
            description="Update contact details, company and tags."
          />
          <DialogBody>
            <CustomerFormStack form={form} />
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={saving}
              disabled={saving || !form.formState.isDirty}
            >
              Save changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
