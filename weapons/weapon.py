from abc import ABC, abstractmethod
from typing import List

import pygame.math

import math

from body import ConstantVelocityBody
from weapons import helpers, constants


class Weapon(ABC):
    def __init__(self, fire_rate_hz: float):
        """
        :param fire_rate_hz: the rate at which the weapon may be fired
        """
        self.fire_rate_hz = fire_rate_hz
        self.seconds_per_shot = 1 / self.fire_rate_hz
        # Initialize to a value where they can shoot immediatly
        self.time_since_last_shot: float = self.seconds_per_shot

    @abstractmethod
    def fire(self, firing_position: pygame.math.Vector2, aim_angle: float):
        pass


class HitscanBeam:
    """A hitscan beam is a shot from a weapon"""

    def __init__(
        self,
        start_point: pygame.math.Vector2,
        end_point: pygame.math.Vector2,
        collision_force,
        damage,
    ):
        self.delta_y = end_point[1] - start_point[1]
        self.delta_x = end_point[0] - start_point[0]

        self.direction_vector = (end_point - start_point).normalize()

        self.start_point = start_point
        self.end_point = end_point

        self.damage = damage

        self.collision_force = collision_force

        self.slope = helpers.get_slope(start_point, end_point)

        self.quadrant_info = (
            helpers.get_sign(self.delta_x),
            helpers.get_sign(self.delta_y),
        )


class HitscanWeapon(Weapon, ABC):
    """
    A hitscan weapon is a weapon that fires instantly
    """

    def __init__(self, fire_rate: float, damage: int):
        """
        Set up a hitscan weapon

        :param damage: the amount of damage that a successful hit will do
        """
        super().__init__(fire_rate_hz=fire_rate)
        self.damage = damage

    @abstractmethod
    def fire(
        self, firing_position: pygame.math.Vector2, aim_angle: float
    ) -> List[HitscanBeam]:
        """
        :param firing_position: the position that the weapon is fired at
        :param aim_angle: the angle that the weapon is fired at
        :return: List[HitscanBeam]
        """
        pass


class ProjectilePayload(ABC):
    """Something that happens when a projectile is done moving"""

    @abstractmethod
    def activate(self, pos: pygame.math.Vector2):
        pass


class HitscanProjectilePayload(ABC):
    """This class represents any type of payload that produces hitscan beams"""

    @abstractmethod
    def activate(self, pos: pygame.math.Vector2) -> List[HitscanBeam]:
        pass


class RadialExplosives(HitscanProjectilePayload):
    def __init__(self, radius=100, power=750, num_shards=32):
        self.radius = radius
        self.power = power
        self.num_shards = num_shards

    def activate(self, pos: pygame.math.Vector2) -> List[HitscanBeam]:
        """
        Activates the explosives at the given location and returns the beams generated by it

        :param pos: the location for the explosives to be set off
        :return: List[HitscanBeam]
        """
        explosion_beams = []
        angle_fraction = math.tau / self.num_shards
        for i in range(self.num_shards):
            angle = angle_fraction * i
            x, y = helpers.polar_to_cartesian(self.radius, angle)
            relative_shard_vec = pygame.math.Vector2(x, y)
            shard_vec = relative_shard_vec + pos
            explosion_beams.append(HitscanBeam(pos, shard_vec))
        return explosion_beams


class Projectile:
    """An object that moves in a linear path and then activates a payload"""

    def __init__(self, payload: HitscanProjectilePayload):
        self.payload = payload


class Launcher(Weapon, ABC):
    """A launcher is a weapon which fires a single projectile"""

    def __init__(self, fire_rate: float):
        """
        Set up a launcher weapon
        """
        super().__init__(fire_rate_hz=fire_rate)

    @abstractmethod
    def fire(
        self, firing_position: pygame.math.Vector2, aim_angle: float
    ) -> Projectile:
        """
        :param aim_angle: the angle that the weapon is fired at
        :return: Projectile
        """
        pass
