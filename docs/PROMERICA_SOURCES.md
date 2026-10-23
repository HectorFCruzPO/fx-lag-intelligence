# Promerica Costa Rica USD compra: source and access review

Research date: 2026-10-23 (Costa Rica). Status: **discovery only; no Promerica collector, scheduler or authenticated integration implemented**. This review builds on [DATA_SOURCES.md](DATA_SOURCES.md) and the [PRD](PRD.md).

## Target rate and decision

The owner confirmed that they normally sell USD through **Promerica online banking or its mobile app**, not at a branch. The project use case is selling USD 3,000 every 15 days for CRC. Compra is the bank buying the owner's dollars; venta is the opposite direction.

**Decision:** do not treat the public branch quote as the owner's executable online/app rate yet. No documented public exchange-rate API/feed, automation permission, numeric request limit, update cadence or USD 3,000 channel applicability was verified in the material reviewed. This does not establish that a supported feed is unavailable. Ask the bank for the applicable source and permitted method before implementing scheduled collection.

The BCCR collector, protected token, CSV and weekday task are unchanged by this research. Do not reuse BCCR indicator 317 as a Promerica rate.

## Evidence and limits

The web research tool returns extracted/indexed content and may serve cached material. "Fetched" below means a page was opened through that tool, not a successful Python adapter, fresh executable quote or authenticated bank request. No banking credentials, private account data or API secrets were requested or accessed.

| Official source | What was observed | What it does not establish |
| --- | --- | --- |
| [Bank homepage](https://www.promerica.fi.cr/) and [alternate bank landing page](https://www.promerica.fi.cr/banco-promerica-costa-rica/) | Homepage open timed out. The alternate page exposed dollar/euro compra/venta labels and a history link, but no numeric rate cells in extracted text. | No usable live numeric payload, source timestamp, update cadence or API contract. Dynamic loading/caching are possibilities, not verified causes. |
| [Branch exchange-rate page](https://www.promerica.fi.cr/tipo-de-cambio-sucursales/) | Fetched text showed USD/CRC compra and venta, a warning that prices can vary with market conditions, and a separate accounting-reference section. No effective date/time appeared in the extracted rate content. | The numerical snapshot is not proof of today's executable rate or equivalence to online/app prices. The accounting reference must be excluded. No authenticated quote or USD 3,000 comparison was performed. |
| [History form](https://www.promerica.fi.cr/historial/tipo-de-cambio/seccion/) | Extracted form had two selectors and a consultation button. Historical records were not retrieved or validated. | No verified historical coverage, schema, daily/intraday meaning, revisions or permitted extraction method. |
| [Digital channels](https://www.promerica.fi.cr/promerica-digital/canales-digitales/) | Public descriptions identify mobile and online channels. | No verified equality between their FX quotes and public branch prices. |
| [Business plans](https://www.promerica.fi.cr/empresas/soluciones-empresariales/planes-empresariales/) | The bank advertises foreign-exchange services and preferential conditions for some business products. | No conclusion that the owner's personal USD 3,000 conversion qualifies for those products or their rates. |
| [Current-discovery fee document](https://www.promerica.fi.cr/media/ewahvma0/25022026-tarifario-cuentas-de-efectivo.pdf) | This official PDF was readable and lists account/transfer services and charges. | No verified net cost or fee exemption for the owner's specific USD-to-CRC online/app transaction. Do not equate a transfer fee category with currency-conversion pricing. |

No rate found in this research is promoted to a collector observation or executable quote. Publication/effective time remains unknown where not explicitly supplied. A retrieval timestamp alone cannot establish freshness.

## Robots guidance and terms

[Promerica's robots.txt](https://www.promerica.fi.cr/robots.txt) was readable. Its general user-agent rules include the pattern `/*seccion*`, which matches the history URL above, plus disallowed paths such as `/scripts/` and several JavaScript assets. The branch-rate path is not explicitly excluded by the rules observed.

Robots guidance concerns crawling, not contractual authorization or a data-use license. A path not being excluded does **not** establish permission to poll, retain, redistribute or use data in alerts. The history/script restrictions are a reason to seek a supported feed rather than build a crawler around excluded routes. No scheduled Promerica polling, endpoint guessing, login automation or restriction bypass was started.

The official landing page's terms link led to [website terms PDF](https://www.promerica.fi.cr/media/491366/terminos-y-condiciones-web.pdf). The research tool identified a 17-page PDF but exposed no readable text; screenshot attempts did not provide inspectable content in this environment. Its detailed clauses were therefore **not verified**. No claim is made that the terms either authorize or categorically prohibit this specific project.

An official [electronic-services contract page](https://www.promerica.fi.cr/personas/contratos-y-reglamentos/contrato-de-uso-de-servicios-electronicos-de-banco-promerica/) and search results also surfaced, but they do not supply a verified public FX collection license here. Search results on an `api.promerica.fi.cr` host included terms documents: an API hostname is not evidence of a supported public rate API. No financial/account endpoints were called.

## API, timestamps and polling: unresolved

Targeted searches of official bank pages did not establish an exchange-rate API contract. The following still require bank confirmation:

- A supported public or explicitly authorized structured source, documented URL, response schema and authentication requirements, if any. Do not invent an endpoint or borrow a customer session token.
- Whether its compra quote applies to selling USD 3,000 through online banking/mobile, including personal versus business accounts, preferred/negotiated pricing, fees and amount conditions.
- Numeric request limits, whether one query every 30 minutes is permitted, and what to do after rate limiting.
- Source effective/publication timestamps and timezone, intraday revision behavior, publication cadence, weekends and holidays. Business/branch opening hours do not prove a rate publication window.
- Historical depth and whether historical values are opening, closing, intraday or last-observed quotes.
- Permitted local retention, private comparisons, derived change calculations and eventual notifications; any separate conditions for redistribution.

### Secondary official-source lead

BCCR's [legacy exchange-rate index](https://gee.bccr.fi.cr/indicadoreseconomicos/IndicadoresEconomicos/frmEstructuraInformacion.aspx?codMenu=+71&idioma=1) links an announced-bank-counter-rate table. Following that link to `frmConsultaTCVentanilla.aspx` returned 404 through the research tool. The current [SDDE portal](https://sdd.bccr.fi.cr/es/IndicadoresEconomicos/Inicio/) was also surfaced in search results for intermediary counter rates.

This is a research lead only. No current Promerica bank-specific SDDE code, payload, reporting delay or automation entitlement was verified. Bank counter rates reported through BCCR are a different series from BCCR reference indicator 317 and are not automatically the owner's online/app quote. Do not substitute either without validating meaning and applicability.

## Next evidence to obtain

1. Ask Promerica which supported source represents the owner's channel and permits automated reading/retention at the chosen interval. Record the written answer, date and applicable conditions without private account details.
2. Once a candidate is confirmed, the owner can manually compare its compra quote against the quote shown in their usual online/app channel at approximately the same time. Record amount USD 3,000, channel, date, time/timezone, rate and any visible fee/applicability notes. Do not execute a trade solely for this check or share account numbers, balances, passwords, OTPs, cookies or session tokens.
3. Repeat a small simultaneous comparison at several times. Agreement at one time is useful evidence but not proof of permanent equality or an executable-price guarantee.
4. Choose a clearly labeled series identity before coding: public branch quote, public general quote, authorized channel-specific quote or owner-recorded quote. Do not mix them into one history.
5. Implement the smallest adapter only after the access/mapping questions are resolved. Use synthetic tests first. Keep the existing BCCR task independent and do not enable actionable cross-source alerts while required inputs or freshness are unverified.

If a supported automated source cannot yet be established, manual owner-recorded quotes can support an explicitly labeled research sample. No manual-entry feature was built in this discovery step.

## Message the owner can send to Promerica

The bank's [official customer-service page](https://www.promerica.fi.cr/ayuda/solucion-promerica/) links customer support. Its published contact details include **2519-8090** and **solucion@promerica.fi.cr**. Verify them on the official site before contacting the bank. **No message has been sent by the assistant.**

Suggested inquiry, without private account or credential information:

> Hola. Soy cliente y normalmente vendo USD 3.000 por colones mediante Promerica en Línea o la app. Estoy preparando una herramienta personal de consulta; no realizaría transacciones automáticas.
>
> ¿Qué tipo de cambio de compra publicado corresponde a ese canal y monto? ¿Es el mismo de la página pública o de sucursales, o pueden aplicar precios preferenciales, negociados o comisiones?
>
> ¿Existe una API, archivo o fuente oficial autorizada para consultar automáticamente esa cotización? Si no, ¿permiten consultar la página pública y guardar observaciones localmente para comparación personal? Deseo conocer los límites y si una consulta cada 30 minutos es permitida, antes de programarla.
>
> ¿La fuente incluye fecha/hora de vigencia y zona horaria? ¿Cuál es la frecuencia de actualización, incluyendo fines de semana, feriados y revisiones? ¿Hay histórico diario o intradía?
>
> ¿Qué condiciones aplican a la conservación local, cálculo privado de variaciones y futuras notificaciones personales? Agradecería la documentación técnica y condiciones de uso aplicables.

## Validation of this discovery

Official pages and targeted official-domain search results were reviewed as described above. Missing text, timeouts, cached extractions and the 404 are recorded rather than interpreted as proof of an API's existence or absence. This is a documentation-only change: no new authenticated request, bank login, real conversion, data collection job, paid-service configuration or institution contact occurred. No new Promerica integration success or prediction is claimed.
