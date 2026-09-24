import { apiRequest, ApiError, pageSchema, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { demoSession } from "@/demo/workspace";
import {
  employeeSchema,
  headcountSchema,
  type Employee,
  type EmployeeInput,
  type Headcount,
  type ListParams,
} from "@/features/business/types";

export interface HRService {
  headcount(): Promise<Headcount>;
  employees(params: ListParams & { departmentId?: string }): Promise<Page<Employee>>;
  employee(id: string): Promise<Employee>;
  create(input: EmployeeInput): Promise<Employee>;
  update(id: string, input: Partial<EmployeeInput> & { termination_date?: string | null }): Promise<Employee>;
}

const live: HRService = {
  headcount: () => apiRequest("GET", "/hr/headcount", headcountSchema),
  employees: ({ page = 1, pageSize = 25, search, status, departmentId }) =>
    apiRequest("GET", "/hr/employees", pageSchema(employeeSchema), { query: { page, page_size: pageSize, search, status, department_id: departmentId } }),
  employee: (id) => apiRequest("GET", `/hr/employees/${id}`, employeeSchema),
  create: (input) => apiRequest("POST", "/hr/employees", employeeSchema, { body: input }),
  update: (id, input) => apiRequest("PATCH", `/hr/employees/${id}`, employeeSchema, { body: input }),
};

/** Mirrors the API: compensation is only returned to holders of hr.sensitive. */
function redact(employee: Employee): Employee {
  const sensitive = demoSession()?.permissions.includes("hr.sensitive") ?? false;
  return sensitive
    ? { ...employee, sensitive_visible: true }
    : { ...employee, salary: null, salary_currency: null, sensitive_visible: false };
}

function find(id: string) {
  const employee = demoBusiness().employees.find((e) => e.id === id);
  if (!employee) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return employee;
}

const demo: HRService = {
  async headcount() {
    await demoDelay();
    const employees = demoBusiness().employees;
    const byDept = new Map<string, number>();
    for (const e of employees.filter((e) => e.status !== "terminated")) byDept.set(e.department_name ?? "Unassigned", (byDept.get(e.department_name ?? "Unassigned") ?? 0) + 1);
    return {
      total: employees.length,
      active: employees.filter((e) => e.status === "active").length,
      on_leave: employees.filter((e) => e.status === "on_leave").length,
      terminated: employees.filter((e) => e.status === "terminated").length,
      by_department: [...byDept.entries()].sort((a, b) => b[1] - a[1]),
    };
  },
  async employees({ page = 1, pageSize = 25, search, status, departmentId }) {
    await demoDelay();
    const rows = demoBusiness()
      .employees.filter((e) => (!status || e.status === status) && (!departmentId || e.department_id === departmentId) && (!search || matches(e.full_name, search) || matches(e.job_title, search)))
      .sort((a, b) => a.full_name.localeCompare(b.full_name))
      .map(redact);
    return paginate(rows, page, pageSize);
  },
  async employee(id) {
    await demoDelay();
    return redact(find(id));
  },
  async create(input) {
    await demoDelay(300);
    const business = demoBusiness();
    if ((input.salary || input.salary_currency) && !demoSession()?.permissions.includes("hr.sensitive"))
      throw new ApiError(422, "SENSITIVE_FIELD", undefined, "Compensation needs HR sensitive access");
    const dept = business.departments.find((d) => d.id === input.department_id);
    const employee: Employee = {
      id: demoId("emp"), full_name: input.full_name, email: input.email || null, phone: input.phone || null, job_title: input.job_title,
      department_id: dept?.id ?? null, department_name: dept?.name ?? null, manager_id: input.manager_id || null, employment_type: input.employment_type,
      status: "active", hire_date: input.hire_date, termination_date: null, salary: input.salary || null, salary_currency: input.salary_currency || null,
      sensitive_visible: true, created_at: new Date().toISOString(),
    };
    business.employees.unshift(employee);
    return redact(employee);
  },
  async update(id, input) {
    await demoDelay(250);
    const employee = find(id);
    if (("salary" in input || "salary_currency" in input) && !demoSession()?.permissions.includes("hr.sensitive"))
      throw new ApiError(422, "SENSITIVE_FIELD", undefined, "Compensation needs HR sensitive access");
    Object.assign(employee, input);
    if (input.department_id !== undefined) employee.department_name = demoBusiness().departments.find((d) => d.id === input.department_id)?.name ?? null;
    if (employee.status === "terminated" && !employee.termination_date) employee.termination_date = new Date().toISOString().slice(0, 10);
    return redact(employee);
  },
};

export const hrService = select<HRService>({ demo, live });
