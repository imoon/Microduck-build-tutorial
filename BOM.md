# Prototype ordering BOM

Updated October 24, 2026. Prices below retain the supplier's currency and exclude shipping, tax and import charges. No orders have been placed. This is the electronics order for one prototype; the unresolved mechanical and battery items below prevent calling it a complete kit BOM.

## Order these parts

| Part | Exact part number | Order quantity | Purpose | Price reference and source |
|---|---|---:|---|---|
| ROBOTIS Dynamixel servo | **XL330-M288-T**, ROBOTIS SKU **902-0163-000** | **16** | 10 leg + 4 head/neck + 1 optional beak + 1 spare. The current controller drives 14; beak control remains to be integrated. | [ROBOTIS America](https://robotis.us/products/dynamixel-xl330-m288-t): **US$27.49 each; US$439.84 total**. The page currently warns of an estimated **two-month lead time** and also displays sold-out messaging; this is not confirmed inventory. |
| USB-to-servo controller | **ROBOTIS OpenRB-150**, SKU **902-0183-000** | **1** | Matches the tutorial's USB serial interface. Its USB-to-Dynamixel firmware/setup must be verified during commissioning. | [ROBOTIS America](https://robotis.us/products/openrb-150): **US$28.64**; page displays sold-out messaging. Use it for communication and a small bench setup; its 3 A DXL rail is not the full-robot power distributor. |
| IMU breakout | **Adafruit BNO085, product 4754**, DigiKey **1528-4754-ND** | **1** | Documented BNO08x sensor family, connected over I2C. This exact board still needs electrical and mounting validation with this fork's driver. | [DigiKey Canada](https://www.digikey.ca/en/products/detail/adafruit-industries-llc/4754/13426653): CAD pricing at checkout; recent search listing was **C$36.57**, not a guaranteed quote. |

Motor + controller reference subtotal: **US$468.48**, plus the IMU in CAD. We have not converted currencies or represented this as a delivered CAD quote.

If the [OpenRB-150 Starter Kit](https://robotis.us/products/openrb-150-starter-kit), SKU **902-0184-000**, is available, it includes one XL330-M288-T and one OpenRB-150. Order **one starter kit + fifteen separate motors**, instead of the two ROBOTIS rows above. At the listed US$52.79 kit price, that combination totals **US$465.14**. Verify availability before paying; current and cached stock messages disagree. Do not order both configurations.

The separate [Dukki project](https://github.com/lachlanhurst/dukki) uses Unitree J288 servos. Our fork uses XL330-M288-T; the mechanical interfaces, bus and actuator model are specific to it.

## Included with the retail servo packages

The [manufacturer's package list](https://robotis.us/products/dynamixel-xl330-m288-t) specifies one Robot Cable-X3P 180 mm, six PHS M2x6 TAP screws and ten PHS M2x8 TAP screws per motor. Sixteen retail packages therefore provide:

| Included item | Total |
|---|---:|
| Robot Cable-X3P 180 mm | 16 |
| PHS M2x6 TAP screws | 96 |
| PHS M2x8 TAP screws | 160 |

Confirm the seller is shipping retail packages with these accessories. Bulk/replacement packaging can differ. These quantities do not establish that every required robot fastener is covered; we will map the remaining screws and supports during dry assembly.

## Already available / check before ordering

| Item | Quantity per robot | Current status |
|---|---:|---|
| Bambu X1 Carbon and PLA/PETG/TPU | Shared printer and material stock | Available. Start with PLA for reference rigid parts; source-specific soft-part assignments need review. |
| Current-limited bench supply | Shared | Available. Start single-servo work at a regulated 5.0 V with suitable current limiting. |
| Raspberry Pi **Zero 2 W** | 1 | User has a Pi to locate. Confirm it is a Zero 2 W, not an original Zero W. If needed, [PiShop Canada SC1176](https://www.pishop.ca/product/raspberry-pi-zero-2-w/) lists C$21.95, subject to stock. |
| microSD, 16 GB or greater | 1 | Check existing stock; use a fresh, identified card for the reproducible image. |
| Pi Zero USB OTG adapter + USB data cable to OpenRB USB-C | 1 set | Check existing cables. A charge-only cable will not carry the servo bus connection. |
| BNO085 header / short I2C leads | 1 set | Check existing stock and breakout pinout; Pi GPIO signalling is 3.3 V. |
| Bluetooth gamepad | 1, or shared | Optional; keyboard control is available. |

## Specify after the first bench and mechanical checks

- Battery, charger, regulator, fuse, switch, power distribution and high-current harness: define the actual full-charge and transient voltages, measured loads, connectors and weights first. The retail XL330 accepts **3.7–6.0 V**, with **5 V recommended**; a directly connected 2S lithium pack reaches 8.4 V and is unsuitable. [ROBOTIS specification](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/).
- The [OpenRB-150 specification](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/) limits its DXL rail to **3 A**. Route the robot's servo power through an appropriately rated separate distribution design; do not assume a higher-voltage VIN rating applies to the servos.
- Fastener lengths by assembly, POM/steel shim dimensions and quantities, and any purchased bearings: upstream only says “several.” We will not invent order quantities from renderings or simulation placeholders.
- Shorter servo cables and power-injection harness: select after routing and voltage-drop measurements. Use the included cables for the initial bench work.

## Team kits

Team quantity has not been specified. For a frozen 15-servo kit, budget **15 motors per robot plus a shared spare pool**, one controller, one IMU and one verified Pi per robot. The first prototype's extra spare is not automatically required in every kit. Buy one prototype configuration before a team quantity: firmware version, servo configuration, cable routing, measured power, fastener counts and print tolerances must be recorded first.
