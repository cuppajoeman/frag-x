import pygame, queue
import commands
import game_engine_constants
import map_loading
import dev_constants
import managers
import client_server_communication
import player
import game_modes
import helpers
import pickle
import random
import math
import argparse

from player import ClientPlayer
from converters import str_to_player_data_no_dt
from threading import Thread, Lock
from fractions import Fraction
from network import Network

def mock_server(server_game_manager):
    """This function gets run as a thread and simulates what the server does so we can update the players view without waiting for the server responce, when the server responce comes then we can check positions and fix them if required"""
    while True:
        (
            player_id,
            dx,
            dy,
            dm,
            delta_time,
            firing,
            weapon_request,
        ) = game_engine_constants.MOCK_SERVER_QUEUE.get()

        input_message = client_server_communication.InputNetworkMessage(
            player_id, dx, dy, dm, delta_time, firing, weapon_request
        )

        server_game_manager.perform_all_server_operations(delta_time, input_message)

def game_state_watcher(client_game_manager, network):
    # CONNECT LOOP
    while True:
        size_bytes = helpers.recv_exactly(network.socket, 4)
        size = int.from_bytes(size_bytes, "little")
        message = pickle.loads(helpers.recv_exactly(network.socket, size))
        client_game_manager.client_message_parser.run_command_from_message(message)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip_address', '-i', type=str, 
                        default=game_engine_constants.DEFAULT_IP,
                        help='ip to connect to server on')
    parser.add_argument('--port', '-p', type=int, 
                        default=game_engine_constants.DEFAULT_PORT,
                        help='port to connect to server on')
    return parser.parse_args()

def run_client(args):
    # logging.basicConfig(level=logging.INFO)

    # START MAP LOAD TODO server should only send the name of the map and then we load it in

    map_grid = map_loading.MapGrid(map_loading.get_pixels(game_engine_constants.DEV_MAP))
    partitioned_map_grid = map_loading.PartitionedMapGrid(
        map_loading.get_pixels(game_engine_constants.DEV_MAP), 10, 10
    )

    # END MAP LOAD

    ## initialize pygame and create window
    pygame.init()
    pygame.mixer.init()  ## For sound
    pygame.font.init()  # you have to call this at the start,

    font = pygame.font.SysFont(pygame.font.get_default_font(), 30)

    if game_engine_constants.FULL_SCREEN:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        (
            game_engine_constants.WIDTH,
            game_engine_constants.HEIGHT,
        ) = pygame.display.get_surface().get_size()
        game_engine_constants.SCREEN_CENTER_POINT = (
            game_engine_constants.WIDTH / 2,
            game_engine_constants.HEIGHT / 2,
        )
    else:
        screen = pygame.display.set_mode((game_engine_constants.WIDTH, game_engine_constants.HEIGHT))


    # The client uses the server logic to simulate live reactions
    # and uses the servers responce to fix/verify differences
    if game_engine_constants.CLIENT_GAME_SIMULATION:
        server_game_manager = managers.ServerGameManager(game_engine_constants.DEV_MAP, game_modes.FirstToNFrags(1))
        game_engine_constants.MOCK_SERVER_QUEUE = queue.Queue()

    dev_constants.CLIENT_VISUAL_DEBUGGING = True
    if dev_constants.CLIENT_VISUAL_DEBUGGING:
        dev_constants.SCREEN_FOR_DEBUGGING = screen

    pygame.display.set_caption(game_engine_constants.GAME_TITLE)
    clock = pygame.time.Clock()  # For syncing the FPS

    # Initialize network
    network = Network(game_engine_constants.DEFAULT_IP, args.port, game_engine_constants.BUF_SIZE)
    player_id = network.connect()

    print(f"You are player {player_id}")

    # initially we don't know what our id is we only get it back from the server so we need to do
    # a type of responce thing..
    spawn = random.choice(partitioned_map_grid.spawns)
    rand_color = random.choices(range(256), k=3)
    curr_player = ClientPlayer(
        spawn.pos,
        game_engine_constants.TILE_SIZE,
        game_engine_constants.TILE_SIZE,
        rand_color,
        game_engine_constants.WASD_MOVEMENT_KEYS,
        game_engine_constants.WEAPON_KEYS,
        player_id,
        network,
    )

    client_game_manager = managers.ClientGameManager(screen, font, game_engine_constants.DEV_MAP, curr_player, network)

    ## group all the sprites together for ease of update
    # TODO REMOVE THIS AND JUST USE A SET
    client_game_manager.all_sprites = pygame.sprite.Group()

    client_game_manager.all_sprites.add(curr_player)

    client_game_manager.id_to_player[player_id] = curr_player

    if game_engine_constants.CLIENT_GAME_SIMULATION:
        # "connecting"
        mock_socket = None
        # not using .add_player because that would generate a different id
        server_game_manager.id_to_player[player_id] = player.KillableServerPlayer(
            game_engine_constants.SCREEN_CENTER_POINT, 50, 50, player_id, mock_socket
        )  # for testing out first to n frags
        # SGM.id_to_player[player_id] = player.ServerPlayer(game_engine_constants.SCREEN_CENTER_POINT, 50, 50, player_id, mock_socket)

    t = Thread(target=game_state_watcher, args=(client_game_manager, network))
    t.start()

    if game_engine_constants.CLIENT_GAME_SIMULATION:
        mock_server_thread = Thread(target=mock_server, args=(server_game_manager))
        mock_server_thread.start()

    # Game loop
    running = True
    ticks_from_previous_iteration = 0

    # Initialization
    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)

    while running:
        # 1 Process input/events
        clock.tick(game_engine_constants.FPS)  ## will make the loop run at the same speed all the time

        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False

        # 2 Update

        t = pygame.time.get_ticks()
        # deltaTime in seconds.
        delta_time = (t - ticks_from_previous_iteration) / 1000.0
        ticks_from_previous_iteration = t

        message_to_send = ""

        if not client_game_manager.is_typing:
            if helpers.started_typing(events):  # only check if they pressd when not typing
                client_game_manager.is_typing = True
                just_started = True
        else:
            if helpers.ended_typing_and_do_action(
                events
            ):  # they are typing and then press return
                client_game_manager.is_typing = False
                # DO ACTION
                message = client_game_manager.user_text_box.text
                if commands.is_command(message):
                    full_command = message
                    successful = (
                        client_game_manager.client_command_runner.attempt_run_command(
                            full_command
                        )
                    )
                    if successful:
                        print("command went through!")
                    else:
                        print("command failed")
                else:
                    # then we're dealing with a normal chat message
                    message_to_send = message

                # print(f"sending {client_game_manager.user_text_box.text}")
                client_game_manager.user_text_box.text = ""
            elif helpers.ended_typing_and_do_nothing(events):
                client_game_manager.is_typing = False
                client_game_manager.user_text_box.text = ""

        if client_game_manager.is_typing and not just_started:
            client_game_manager.user_text_box.update(
                events
            )  # update the textbox if they're typing

        just_started = False

        # Note: This sends the users inputs to the server
        client_game_manager.all_sprites.update(events, delta_time)

        curr_player.send_inputs(
            delta_time, client_game_manager.is_typing, message_to_send
        )

        # 3 Draw/render
        screen.fill(pygame.color.THECOLORS["black"])

        client_game_manager.player_data_lock.acquire()
        for row in partitioned_map_grid.partitioned_map:
            for partition in row:
                pygame.draw.rect(
                    screen,
                    pygame.color.THECOLORS["gold"],
                    partition.rect.move(curr_player.camera_v),
                    width=1,
                )

                for wall in partition.walls:
                    pygame.draw.rect(
                        screen, wall.color, wall.rect.move(curr_player.camera_v)
                    )

                for b_wall in partition.bounding_walls:
                    pygame.draw.rect(
                        screen, b_wall.color, b_wall.rect.move(curr_player.camera_v)
                    )
        client_game_manager.player_data_lock.release()

        if dev_constants.DEBUGGING_INTERSECTIONS:
            for hit_v in dev_constants.INTERSECTIONS_FOR_DEBUGGING:
                pygame.draw.circle(
                    dev_constants.SCREEN_FOR_DEBUGGING,
                    pygame.color.THECOLORS["purple"],
                    hit_v + curr_player.camera_v,
                    3,
                )

            for partition in dev_constants.INTERSECTED_PARTITIONS_FOR_DEBUGGING:
                pygame.draw.rect(
                    screen,
                    pygame.color.THECOLORS["blueviolet"],
                    partition.rect.move(curr_player.camera_v),
                    width=1,
                )

            for point_v in dev_constants.INTERSECTED_PARTITION_PATCH_MARKERS:
                pygame.draw.circle(
                    dev_constants.SCREEN_FOR_DEBUGGING,
                    pygame.color.THECOLORS["red"],
                    point_v + curr_player.camera_v,
                    3,
                )

            for point_v in dev_constants.INTERSECTED_PARTITION_SEAMS_FOR_DEBUGGING:
                pygame.draw.circle(
                    dev_constants.SCREEN_FOR_DEBUGGING,
                    pygame.color.THECOLORS["yellow"],
                    point_v + curr_player.camera_v,
                    3,
                )

            for beam in dev_constants.BEAMS_FOR_DEBUGGING:
                pygame.draw.line(
                    dev_constants.SCREEN_FOR_DEBUGGING,
                    pygame.color.THECOLORS["green"],
                    beam.start_point + curr_player.camera_v,
                    beam.end_point + curr_player.camera_v,
                )

        client_game_manager.draw_projectiles(curr_player.camera_v)
        client_game_manager.draw_beams(curr_player.camera_v)

        # A drawing is based on a single network message from the server.
        # The reason why it looks like we have shifted tiles is that we received a message in the middle, so this needs to be locked.
        # instead of actually simulating its movement that way it seems more solid
        for sprite in client_game_manager.all_sprites:
            # Add the player's camera offset to the coords of all sprites.
            screen.blit(sprite.image, sprite.rect.topleft + curr_player.camera_v)

        # PLAYER PROPERTIES START

        font_color = pygame.color.THECOLORS["brown3"]

        pos = font.render(str(curr_player.pos), False, font_color)
        aim_angle_str = (
            str(9 - math.floor(curr_player.rotation_angle / math.tau * 10)) + "/" + str(10)
        )
        angle = font.render(aim_angle_str + "τ", False, font_color)

        screen.blit(pos, (0, 25))
        screen.blit(angle, (0, 50))

        # PLAYER PROPERTIES END

        # TEXT BOX START

        client_game_manager.user_chat_box.update_message_times(delta_time)

        client_game_manager.user_chat_box.draw_messages()
        client_game_manager.user_text_box.render_text()

        utb_width, utb_height = client_game_manager.user_text_box.image.get_size()

        screen.blit(
            client_game_manager.user_text_box.image,
            (
                game_engine_constants.WIDTH
                - (utb_width + 2 * client_game_manager.user_text_box.border_thickness),
                game_engine_constants.HEIGHT
                - (utb_height + 2 * client_game_manager.user_text_box.border_thickness),
            ),
        )

        # TEXT BOX END

        ## Done after drawing everything to the screen
        pygame.display.flip()

    pygame.quit()

if __name__ == '__main__':
    args = parse_args()
    run_client(args)
