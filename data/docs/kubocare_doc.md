## Kubocare

KuboCare, is an ambient AI health monitoring platform for senior living, assisted living, memory care, and aging-in-place use cases. Public company information identifies Kubo Care Private Limited as the company behind the service, with Bengaluru, India listed in its privacy policy and public app listing. Public company profile sources also describe the business as B2B and focused on senior living facilities.

KuboCare's public positioning is "ambient care" for seniors: safety and wellness monitoring that runs in the background without requiring seniors to wear a device or be watched by a camera. The company states that it uses AI, radar-based sensing, and a caregiver/family software platform to provide alerts and longitudinal health insights.

## What KuboCare Does

KuboCare's product pages and app listing describe these core capabilities:

1. Fall detection and fall-related alerts.
2. Fall risk assessment and fall prevention features.
3. Movement and activity monitoring.
4. Contactless heart rate and respiratory rate monitoring.
5. Sleep insights, including bed entry/exit, tosses and turns, restless nights, and sleep pattern changes.
6. Environmental monitoring such as air quality, temperature, humidity, and light.
7. Caregiver dashboards and family mobile app visibility.
8. Emergency response workflows through real-time alerts and communication.

The product is positioned for senior care operators and families who need passive monitoring, real-time alerts, and trend visibility without adding daily work for caregivers or requiring seniors to remember a wearable.

## Radar-Based Fall Detection

KuboCare says its devices use radar-based sensing and AI to understand motion, presence, falls, and vital signs. The system is designed to detect falls in real time and to reduce false alarms by differentiating more nuanced fall events from suspected or non-critical events.

Public product material describes these fall-related scenarios and features:

1. Bed falls, including falls while getting in or out of bed.
2. Seated falls, including falls from chairs or wheelchairs.
3. Standing falls.
4. Fall risk assessment.
5. Gait analysis and walking-pattern learning.
6. Behavior-shift detection for unusual movement changes.
7. Pre-fall alerts for early signs of instability.

In simple terms, radar-based fall detection uses radio signals reflected from people and objects in the room. The system analyzes motion, position, and movement patterns rather than capturing images. This makes it suitable for private spaces such as bedrooms and bathrooms where camera-based monitoring may be inappropriate.

## Non-Wearable And No-Camera Model

KuboCare's main product distinction is that it does not require a wearable and does not rely on cameras. The product pages state that it detects motion, falls, and vitals using radar and AI without recording images. The lab page also describes the approach as "no cameras" and based on smart signals.

This matters operationally because:

1. Seniors do not need to remember to wear, charge, or press a device.
2. Monitoring can continue during sleep, bathing-adjacent routines, and other periods when wearables are often removed.
3. There is no video feed for caregivers or family members to view.
4. Private areas can be monitored for safety events without turning them into surveillance spaces.

The assistant should describe this as camera-free and non-wearable monitoring. It should not describe it as "no data at all" because the platform and services still process account, operational, and monitoring data.

## Privacy And Data Handling

KuboCare's privacy message has two separate parts that should not be mixed up:

1. Sensing privacy: public product material says the radar approach avoids cameras and does not record images. This protects dignity in rooms where video monitoring would be intrusive.
2. Platform privacy: the company privacy policy says the website and related services may collect personal and sensitive information such as name, email address, organization, phone number, address, billing data, IP address, device information, site usage, project data, and service interaction data.

The privacy policy also says KuboCare uses security practices such as access controls, multi-factor authentication, security testing, secure device policies, SSDLC practices, continuous monitoring, data minimization, incident response planning, and third-party risk assessment.

The Google Play listing for the KuboCare app currently states that the app developer has declared no data shared with third parties and no data collected, while also showing "Data isn't encrypted." This app-store data-safety statement should be verified against the latest release and privacy policy before making production security claims.

## Safety And Radar Power

KuboCare's FAQ says its radar-based monitoring uses FDA- and FCC-approved sensors and components and operates at low power. The public product FAQ compares a typical Wi-Fi router at roughly 100-1000 mW with KuboCare's millimeter-wave radar at roughly 1-10 mW.

The product FAQ also states that emissions are within international safety standards and that the radar technology is similar to sensing used in motion detectors and automotive safety systems.

When answering safety questions, the assistant should say:

1. KuboCare publicly describes the radar as low-power and non-contact.
2. Radar-based monitoring is not camera surveillance and does not require body contact.
3. Safety claims should be tied to the manufacturer's published specifications and applicable regulatory approvals.
4. The assistant should not give medical or regulatory certification guarantees beyond the public documentation.

## Radar Frequency

KuboCare's public product pages and app listing do not disclose the exact operating frequency or radar band of the deployed device. They describe the technology as millimeter-wave radar and give a power range of 1-10 mW, but power is not the same thing as frequency.

Millimeter-wave radar generally refers to radio frequencies in the millimeter-wave range. Many industrial human-presence and motion-sensing radar chips operate around 60 GHz. For example, Texas Instruments publishes an industrial mmWave radar sensor, IWR6843, with a 60-64 GHz frequency range. Some newer low-power industrial radar variants are published with 57-64 GHz ranges.

Important answering rule: do not claim that KuboCare specifically uses 60 GHz, 60-64 GHz, 57-64 GHz, or any other exact band unless a KuboCare device datasheet, FCC filing, hardware manual, or official technical specification confirms it. If asked "what frequency does KuboCare radar use?", answer that the exact public frequency is not specified; KuboCare publicly describes it only as millimeter-wave radar.

## Installation And Operations

Public product material says KuboCare devices are installed in resident bedrooms and bathrooms. The setup flow describes mounting the device, connecting it to Wi-Fi, and pairing it with the dashboard and mobile app. Product content states setup can be completed in about 10 minutes.

The product FAQ says the current device requires both external power and internet connectivity. If either power or internet is unavailable, monitoring is temporarily interrupted. KuboCare says it is working on future versions with 5G SIM connectivity and UPS backup.

The FAQ also says radar sensors can detect multiple people in a house, but distinguishing individuals is still an area of active work. For shared spaces, KuboCare recommends one device per resident zone to maintain reliable monitoring and event attribution.

## Emergency Response And Care Workflow

KuboCare positions fall detection as part of a broader response workflow. Public pages describe real-time alerts to caregivers, family app visibility, and emergency response coordination. The product FAQ says the device includes a microphone and speaker for two-way communication when an alert is triggered.

For senior living facilities, the intended workflow is that the right staff member receives an alert quickly and can respond without delay. For home use, the system is positioned to connect families or care providers through the app.

## Assistant Answering Guidance

When the user asks what KuboCare is, answer briefly:

KuboCare is an ambient AI health monitoring platform for senior care that uses radar-based, camera-free, non-wearable sensing to monitor falls, activity, sleep, vitals, and room conditions.

When the user asks how fall detection works, answer:

KuboCare uses radar-based sensing and AI to detect motion patterns associated with falls without using cameras or requiring seniors to wear a device. It monitors events such as bed falls, seated falls, standing falls, and activity changes, then alerts caregivers or family through the care platform.

When the user asks about privacy, answer:

KuboCare's sensing approach is privacy-first because it avoids cameras and wearables. It does not rely on video images, but the software platform may still process account, service, device, and operational data according to KuboCare's privacy policy.

When the user asks about radar frequency, answer:

KuboCare does not publicly specify the exact radar frequency in the reviewed product pages. It describes the device as using millimeter-wave radar. Common industrial mmWave radar sensors often operate around 60 GHz, but that should not be stated as KuboCare's exact frequency without an official device specification.

## Source Notes

Primary sources:

1. KuboCare product page: https://kubocare.com/product/
2. KuboCare about page: https://kubocare.com/about-us/
3. KuboCare lab and innovation page: https://kubocare.com/lab-and-innovation/
4. KuboCare privacy policy: https://kubocare.com/privacy-policy/
5. KuboCare Google Play listing: https://play.google.com/store/apps/details?id=com.kubocare

Supporting source for general mmWave context:

1. Texas Instruments IWR6843 product page, a public example of a 60-64 GHz industrial mmWave radar sensor: https://www.ti.com/product/IWR6843

Third-party company profile used only as supporting context:

1. Indexed company profile for Kubo Care: https://indexed.vc/companies/kubo-care

Source quality note: official KuboCare pages are the strongest source for product claims. App-store data safety declarations and third-party company profiles should be treated as supporting context and verified before making contractual, regulatory, or security commitments.
