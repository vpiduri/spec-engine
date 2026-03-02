#!/usr/bin/env node
/**
 * TypeScript schema extractor using ts-morph.
 *
 * Reads: argv[2] = TypeScript file path, argv[3] = type name to extract.
 * Writes JSON Schema to stdout.
 *
 * Exit 0 on success (even if empty {}), exit 1 on unrecoverable error.
 */

'use strict';

let Project;
try {
  ({ Project } = require('ts-morph'));
} catch (e) {
  // ts-morph not installed
  process.stdout.write('{}');
  process.exit(0);
}

const filePath = process.argv[2];
const typeName = process.argv[3];

if (!filePath || !typeName) {
  process.stdout.write('{}');
  process.exit(0);
}

try {
  const project = new Project({ skipAddingFilesFromTsConfig: true });
  const sourceFile = project.addSourceFileAtPath(filePath);

  // Try interface first, then class, then type alias
  let typeDecl =
    sourceFile.getInterface(typeName) ||
    sourceFile.getClass(typeName) ||
    sourceFile.getTypeAlias(typeName);

  if (!typeDecl) {
    process.stdout.write('{}');
    process.exit(0);
  }

  function tsTypeToSchema(typeText) {
    const t = typeText.trim();
    if (t === 'string') return { type: 'string' };
    if (t === 'number') return { type: 'number' };
    if (t === 'boolean') return { type: 'boolean' };
    if (t === 'null' || t === 'undefined') return { type: 'null' };
    if (t === 'Date') return { type: 'string', format: 'date-time' };
    if (t === 'any' || t === 'unknown') return {};
    if (t.endsWith('[]')) {
      const inner = t.slice(0, -2);
      return { type: 'array', items: tsTypeToSchema(inner) };
    }
    if (t.startsWith('Array<') && t.endsWith('>')) {
      const inner = t.slice(6, -1);
      return { type: 'array', items: tsTypeToSchema(inner) };
    }
    if (t.startsWith('Record<') || t.startsWith('Map<')) {
      return { type: 'object', additionalProperties: {} };
    }
    // Union type with null → nullable
    if (t.includes('|')) {
      const parts = t.split('|').map(s => s.trim());
      const nonNull = parts.filter(p => p !== 'null' && p !== 'undefined');
      const isNullable = nonNull.length < parts.length;
      if (nonNull.length === 1) {
        const schema = tsTypeToSchema(nonNull[0]);
        if (isNullable) schema.nullable = true;
        return schema;
      }
    }
    // Named type — use $ref
    return { $ref: `#/components/schemas/${t}` };
  }

  const properties = {};
  const required = [];

  // Interface properties or class properties
  const members =
    typeof typeDecl.getProperties === 'function'
      ? typeDecl.getProperties()
      : [];

  for (const prop of members) {
    const name = prop.getName();
    if (!name || name.startsWith('_')) continue;

    const isOptional =
      typeof prop.hasQuestionToken === 'function'
        ? prop.hasQuestionToken()
        : false;

    let typeText = 'string';
    try {
      typeText = prop.getType().getText();
    } catch (e) {
      try {
        typeText = prop.getTypeNode()
          ? prop.getTypeNode().getText()
          : 'string';
      } catch (e2) {
        typeText = 'string';
      }
    }

    const schema = tsTypeToSchema(typeText);
    if (isOptional) schema.nullable = true;
    properties[name] = schema;

    if (!isOptional) {
      required.push(name);
    }
  }

  const result = {
    type: 'object',
    properties,
  };
  if (required.length > 0) {
    result.required = required;
  }

  process.stdout.write(JSON.stringify(result));
} catch (e) {
  process.stdout.write('{}');
  process.exit(0);
}
