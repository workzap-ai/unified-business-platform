import ts from "typescript";
import fs from "node:fs";
import path from "node:path";

const filename = path.resolve("src/features/pi/types.ts");
const program = ts.createProgram([filename], {
  strict: true,
  target: ts.ScriptTarget.ES2022,
});
const checker = program.getTypeChecker();
const source = program.getSourceFile(filename);
function schema(type) {
  if (type.flags & ts.TypeFlags.StringLiteral)
    return `z.literal(${JSON.stringify(type.value)})`;
  if (type.flags & ts.TypeFlags.NumberLiteral)
    return `z.literal(${type.value})`;
  if (type.flags & ts.TypeFlags.BooleanLiteral)
    return `z.literal(${type.intrinsicName})`;
  if (type.flags & ts.TypeFlags.String) return "z.string()";
  if (type.flags & ts.TypeFlags.Number) return "z.number()";
  if (type.flags & ts.TypeFlags.Boolean) return "z.boolean()";
  if (type.flags & ts.TypeFlags.Null) return "z.null()";
  if (type.flags & ts.TypeFlags.Undefined) return "z.undefined()";
  if (type.isUnion()) return `z.union([${type.types.map(schema).join(",")}])`;
  if (checker.isArrayType(type))
    return `z.array(${schema(checker.getTypeArguments(type)[0])})`;
  const index = type.getStringIndexType();
  if (index) return `z.record(z.string(),${schema(index)})`;
  if (type.flags & ts.TypeFlags.Object)
    return `z.object({${type
      .getProperties()
      .map(
        (p) =>
          `${JSON.stringify(p.name)}:${schema(checker.getTypeOfSymbolAtLocation(p, p.valueDeclaration ?? p.declarations?.[0] ?? source))}${p.flags & ts.SymbolFlags.Optional ? ".optional()" : ""}`,
      )
      .join(",")}})`;
  throw new Error(`Unsupported contract: ${checker.typeToString(type)}`);
}
const output = [
  "// Generated from types.ts by scripts/generate-pi-contracts.mjs. Do not edit.",
  'import { z } from "zod";',
  'import type * as Pi from "./types";',
];
for (const node of source.statements) {
  if (
    !ts.isTypeAliasDeclaration(node) ||
    !node.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)
  )
    continue;
  output.push(
    `export const ${node.name.text}Schema: z.ZodType<Pi.${node.name.text}> = ${schema(checker.getTypeFromTypeNode(node.type))};`,
  );
}
fs.writeFileSync(
  "src/features/pi/contracts.generated.ts",
  output.join("\n") + "\n",
);
