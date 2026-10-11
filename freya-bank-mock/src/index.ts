import { ownerOfFullCardKey, resolveFixture, type Fixture } from "./fixtures.ts";

const PREFIX = "/voice/v1/";
const SERVICES = new Set([
  "cards.list", "cards.balance", "statement.week.get",
  "statement.week.decide", "statement.week.change",
  "contact.email.get", "statement.pdf.send",
]);

function result(code: string, message: string, type: "ERROR" | "WARNING") {
  const guid = crypto.randomUUID().replaceAll("-", "");
  return {
    result: {
      guid, returnCode: code, messageText: message, code, message, type,
      details: { guid, rootCause: type === "WARNING" ? "NotFoundException" : "InvalidArgumentsException", errorOrigin: "ivr-gateway-test:ivr-channel-v0" },
    },
  };
}

function error(status: number, code: string, message: string, type: "ERROR" | "WARNING" = "ERROR") {
  return Response.json(result(code, message, type), { status });
}

function invalid(field: string) {
  return error(400, "INVALID_ARGUMENTS_ERROR", `${field} cannot be empty`);
}

function notFound(service: string) {
  const errors: Record<string, [number, string, string]> = {
    "cards.list": [404, "FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."],
    "cards.balance": [404, "FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı"],
    "statement.week.get": [404, "FB_IVR_CHANNEL_121", "Card not found"],
    "statement.pdf.send": [404, "FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"],
  };
  const specified = errors[service];
  return specified
    ? error(specified[0], specified[1], specified[2], "WARNING")
    : invalid(service === "contact.email.get" ? "customerNo" : "cardNumber");
}

function nonempty(value: unknown): boolean {
  return (typeof value === "string" && value.trim().length > 0) ||
    (typeof value === "number" && Number.isFinite(value));
}

function customerNumber(value: unknown): string | undefined {
  const asString = typeof value === "string" || typeof value === "number" ? String(value) : "";
  return /^\d{8}$/.test(asString) ? asString : undefined;
}

function cardNumber(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function requestedWeek(value: unknown): string | undefined {
  const week = typeof value === "number" || typeof value === "string" ? String(value) : "";
  return /^[1-4]$/.test(week) ? week : undefined;
}

function required(data: Record<string, unknown>, field: string): Response | undefined {
  return nonempty(data[field]) ? undefined : invalid(field);
}

async function fixtureResponse(fixture: Fixture): Promise<Response> {
  if (fixture.delaySeconds !== undefined) {
    await new Promise((resolve) => setTimeout(resolve, fixture.delaySeconds! * 1000));
  }
  return Response.json(fixture.response, { status: fixture.http });
}

async function serviceResponse(service: string, request: Request): Promise<Response> {
  let envelope: unknown;
  try {
    envelope = await request.json();
  } catch {
    return invalid("data");
  }
  if (!envelope || typeof envelope !== "object" || !Object.hasOwn(envelope, "data")) return invalid("data");
  const data = (envelope as { data: unknown }).data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return invalid("data");
  const fields = data as Record<string, unknown>;

  if (service === "cards.list") {
    const missing = required(fields, "customerNo");
    if (missing) return missing;
    const customer = customerNumber(fields.customerNo);
    if (!customer) return invalid("customerNo");
    const fixture = resolveFixture(customer, service);
    return fixture ? fixtureResponse(fixture) : notFound(service);
  }

  if (service === "contact.email.get") {
    for (const field of ["customerNo", "intAddressInfoType"]) {
      const missing = required(fields, field);
      if (missing) return missing;
    }
    const customer = customerNumber(fields.customerNo);
    if (!customer) return invalid("customerNo");
    if (!["E", "P", "B"].includes(String(fields.intAddressInfoType))) return invalid("intAddressInfoType");
    const fixture = resolveFixture(customer, service);
    return fixture ? fixtureResponse(fixture) : notFound(service);
  }

  const cardMissing = required(fields, "cardNumber");
  if (cardMissing) return cardMissing;
  const card = cardNumber(fields.cardNumber);
  if (!card) return invalid("cardNumber");

  if (service === "statement.pdf.send") {
    for (const field of ["customerNo", "currencyType", "statementDate", "emailAddress"]) {
      const missing = required(fields, field);
      if (missing) return missing;
    }
    const customer = customerNumber(fields.customerNo);
    if (!customer) return invalid("customerNo");
    if (!["TL", "USD", "EUR", "GBP"].includes(String(fields.currencyType))) return invalid("currencyType");
    if (typeof fields.statementDate !== "string" || !/^\d{2}\.\d{2}\.\d{4}$/.test(fields.statementDate)) return invalid("statementDate");
    if (ownerOfFullCardKey(card) !== customer) return notFound(service);
    const fixture = resolveFixture(customer, service);
    return fixture ? fixtureResponse(fixture) : notFound(service);
  }

  const customer = ownerOfFullCardKey(card);
  if (!customer) return notFound(service);
  let selectors = [card];
  if (service === "statement.week.decide" || service === "statement.week.change") {
    for (const field of ["newStatementWeek", "statementDay"]) {
      const missing = required(fields, field);
      if (missing) return missing;
    }
    const week = requestedWeek(fields.newStatementWeek);
    if (!week) return invalid("newStatementWeek");
    if (typeof fields.statementDay !== "number" || !Number.isInteger(fields.statementDay)) return invalid("statementDay");
    selectors = [card, week];
  }
  const fixture = resolveFixture(customer, service, selectors);
  return fixture ? fixtureResponse(fixture) : notFound(service);
}

export default {
  fetch(request: Request): Response | Promise<Response> {
    const path = new URL(request.url).pathname;
    if (request.method === "GET" && path === "/health") {
      return Response.json({ status: "ok", bankServicesReady: true }, { status: 200 });
    }
    if (!path.startsWith(PREFIX) || !SERVICES.has(path.slice(PREFIX.length))) {
      return error(404, "NOT_FOUND", "Unknown service");
    }
    if (request.method !== "POST") return error(405, "METHOD_NOT_ALLOWED", "POST required");
    return serviceResponse(path.slice(PREFIX.length), request);
  },
};
