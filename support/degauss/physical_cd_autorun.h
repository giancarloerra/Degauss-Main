#pragma once

// Polls for newly inserted game CDs while Degauss is active. A matching MGL
// from an installed physical-CD provider is returned to Degauss through the
// normal frontend launch handoff.
void physical_cd_autorun_poll(void);
