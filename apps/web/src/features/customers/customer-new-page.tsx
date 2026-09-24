"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { PageHeader, PageShell, RequirePermission } from "@/components/app/page";
import { FormActions, useUnsavedChangesWarning } from "@/components/app/forms";
import { Card } from "@/components/ui/display";
import { useScopedMutation } from "@/hooks/use-scoped";
import { customersService } from "./service";
import {
  applyCustomerServerError,
  customerFormSchema,
  CustomerFormSections,
  emptyCustomerForm,
  formToInput,
  type CustomerFormValues,
} from "./components/customer-form";

export function CustomerNewPage() {
  return (
    <RequirePermission permission="customers.write" area="adding customers">
      <CustomerNew />
    </RequirePermission>
  );
}

function CustomerNew() {
  const router = useRouter();
  const form = useForm<CustomerFormValues>({
    resolver: zodResolver(customerFormSchema),
    defaultValues: emptyCustomerForm,
  });
  const dirty = form.formState.isDirty;
  useUnsavedChangesWarning(dirty && !form.formState.isSubmitSuccessful);

  const create = useScopedMutation((values: CustomerFormValues) => customersService.create(formToInput(values)), {
    invalidate: [["customers"]],
    success: (c) => `${c.name} added`,
    error: "The customer couldn't be saved. Check the details and try again.",
  });

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const customer = await create.mutateAsync(values);
      router.push(`/customers/${customer.id}`);
    } catch (error) {
      applyCustomerServerError(form, error);
    }
  });

  return (
    <PageShell width="default">
      <PageHeader
        title="Add customer"
        description="Create a customer record your team and PI can use for quotes, orders and conversations."
      />
      <form onSubmit={onSubmit} noValidate>
        <Card className="p-5 sm:p-6">
          <CustomerFormSections form={form} />
        </Card>
        <FormActions
          dirty={dirty}
          saving={create.isPending || form.formState.isSubmitting}
          onCancel={() => router.push("/customers")}
          submitLabel="Create customer"
        />
      </form>
    </PageShell>
  );
}
